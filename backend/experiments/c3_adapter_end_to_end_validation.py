"""Fresh synthetic DB only. No index creation, other DB data or cleanup/migration."""
import hashlib
import json
import time
import tracemalloc
from pathlib import Path
from collections import Counter

from bson import BSON
from bson.binary import Binary
from bson.decimal128 import Decimal128
from bson.int64 import Int64
from bson.objectid import ObjectId
from bson.timestamp import Timestamp
from pymongo import MongoClient, monitoring
from pymongo.errors import ConnectionFailure
from pymongo.write_concern import WriteConcern

from backend.history_keys import derive_history_keys
from backend.experiments.c3_history_provision_contract import Target,Authorization,Observation
from backend.experiments.c3_consistent_diagnosis_prototype import run_diagnosis,Limits
from backend.experiments.c3_snapshot_mongodb_reader import MongoSnapshotReader,URI

NAME='test_c3_adapter_d2d2f6a3991c4397b55059264c0a4835'
ENV='b939b0c3-3183-47a9-b958-840249d36c42'
RESULT='backend/experiments/results/'+NAME+'.json'

class Audit(monitoring.CommandListener):
    def __init__(self):self.foreign=[];self.names=Counter();self.anchors=Counter();self.snapshot_diagnostic_roots=0;self.bad_snapshot=[];self.expected_T=None;self.max_reply=Counter();self.reply_bytes=Counter();self.getmore_with_maxTimeMS=0
    def started(self,e):
        self.names[(e.database_name,e.command_name)]+=1
        if e.database_name!=NAME and not (e.database_name=='admin' and e.command_name in {'hello','ismaster','isMaster','buildInfo','listDatabases','endSessions'}):self.foreign.append((e.database_name,e.command_name))
        if e.database_name==NAME and e.command_name=='getMore' and 'maxTimeMS' in e.command:self.getmore_with_maxTimeMS+=1
        if self.expected_T is not None and e.database_name==NAME and (e.command.get('find')=='transactions' or e.command.get('aggregate')=='transactions'):
            rc=e.command.get('readConcern',{})
            if rc!={'level':'snapshot','atClusterTime':self.expected_T}:self.bad_snapshot.append(e.command_name)
            self.snapshot_diagnostic_roots+=1
        if e.database_name==NAME and e.command_name in ('find','aggregate'):
            rc=e.command.get('readConcern',{});t=rc.get('atClusterTime')
            if rc.get('level')=='snapshot' and type(t) is Timestamp:self.anchors[(t.time,t.inc)]+=1
    def succeeded(self,e):
        size=len(BSON.encode(e.reply));self.max_reply[e.command_name]=max(self.max_reply[e.command_name],size);self.reply_bytes[e.command_name]+=size
    def failed(self,e):pass

def physical(i):
    return (i if i%6==0 else Int64(i) if i%6==1 else f'synthetic-{i:06}' if i%6==2 else
            Binary(i.to_bytes(8,'big'),0 if i%6==3 else 1) if i%6 in (3,4) else ObjectId(i.to_bytes(12,'big')))

def row(i):
    r={'_id':physical(i),'id':f'synthetic-logical-{i//2:06}','user_id':'default-user',
       'date':'20261001T120000.123456Z','amount':Decimal128('70.1200')}
    if i%5!=1:
        if i%5==3:r['date']='invalid-synthetic'
        r['_history_keys']=derive_history_keys(r,1)
        if i%5==2:r['amount']=Decimal128('71')
        if i%5==4:r['_history_keys']['generation']=2
    return r

def rss():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])*1024

def main():
    audit=Audit()
    def connect():return MongoClient(URI,serverSelectionTimeoutMS=3000,connectTimeoutMS=3000,socketTimeoutMS=15000,event_listeners=[audit])
    setup=connect();result={'database':NAME,'scenarios':{},'metrics':{},'certificate_issued':False}
    def ok(name,details):result['scenarios'][name]={'passed':True,**details};print(name+': OK',flush=True)
    try:
        hello=setup.admin.command('hello')
        assert setup.address==('127.0.0.1',27018) and hello['isWritablePrimary'] and hello['setName']=='app_finanzas_dev_rs'
        assert NAME not in setup.list_database_names()
        result['server_version']=setup.admin.command('buildInfo')['version'];assert result['server_version'].startswith('8.0.')
        db=setup.get_database(NAME,write_concern=WriteConcern('majority'))
        metadata={'_id':'financial-context','version':1,'environment_id':ENV,'created_at':'2026-10-13T00:00:00Z'}
        db.moneyflow_metadata.insert_one(metadata);coll=db.create_collection('transactions')
        uuid=list(db.list_collections(filter={'name':'transactions'}))[0]['info']['uuid']
        for start in range(0,2001,500):coll.insert_many([row(i) for i in range(start,min(start+500,2001))])
        with setup.start_session(causal_consistency=False) as session:
            reply=db.command({'find':'transactions','filter':{'user_id':'default-user'},'batchSize':1,'singleBatch':True,
                              'readConcern':{'level':'snapshot'},'maxTimeMS':10000},session=session)
            T=reply.get('atClusterTime') or reply['cursor'].get('atClusterTime');assert type(T) is Timestamp
        target=Target(URI,NAME,'transactions',uuid,ENV)
        auth=Authorization(target,'synthetic-e2e','4585e5293b7466f3a58c7faf783bd8707253d8ac',1,1,('diagnose',),approved=True)
        obs=Observation(target,metadata)
        result['T']={'seconds':T.time,'increment':T.inc};result['environment_id']=ENV;result['collection_uuid']=bytes(uuid).hex()
        ok('isolation_and_server_T',{'absent_before_first_write':True,'R6_synthetic':True})
        def execute(name,limits=Limits(),anchor=T,hook=None):
            client=connect();before=rss();start=time.perf_counter();tracemalloc.start()
            more_before=audit.names[(NAME,'getMore')];audit.expected_T=anchor
            try:
                with MongoSnapshotReader(client,auth,obs,anchor,own_client=True,before_getmore=hook) as reader:
                    report=run_diagnosis(reader,auth,obs,anchor,limits=limits)
                peak=tracemalloc.get_traced_memory()[1]
            finally:tracemalloc.stop();audit.expected_T=None
            result.setdefault('reports',{})[name]=report
            assert not reader.active and reader.closed and reader.metrics['sessions_opened']==reader.metrics['sessions_closed']
            assert reader.metrics['cleanup_errors']==0
            result['metrics'][name]={'wall_ms':round((time.perf_counter()-start)*1000,3),'python_peak_bytes':peak,
                'rss_before':before,'rss_after':rss(),'getmore_commands':audit.names[(NAME,'getMore')]-more_before,'reader':dict(reader.metrics),'anchors':[list(x) for x in reader.anchors]}
            return report
        baseline=execute('baseline',Limits(batch_documents=50))
        assert baseline['complete_at_T'] and not baseline['keys_ready_at_T']
        assert baseline['visited']==2001 and baseline['duplicate_groups']==1000
        assert baseline['counts']=={'ready':401,'missing':400,'stale_or_corrupt':400,'unverifiable':400,'incompatible':400}
        ok('complete_diagnosis_at_T',baseline)
        coll.insert_many([{'_id':-1,'id':'synthetic-new-early','user_id':'default-user','date':'2026-10-13','amount':1},
                          {'_id':ObjectId(b'\xff'*12),'id':'synthetic-new-late','user_id':'default-user','date':'2026-10-13','amount':1}])
        coll.update_one({'_id':0},{'$set':{'amount':Decimal128('99')}});coll.delete_one({'_id':Int64(1)})
        second=execute('post_T_writes',Limits(batch_documents=100))
        for key in ('counts','visited','duplicate_groups','extra_duplicate_documents','source_unverifiable','complete_at_T'):
            assert second[key]==baseline[key]
        assert coll.count_documents({})==2002
        ok('post_T_writes_preserve_view',{'snapshot_count':second['visited'],'live_count':2002,'counts_identical':True,'duplicates_identical':True})
        # Actual server cursor kill inside only this synthetic DB.
        injected=[]
        def kill(reader,h):
            if not injected:
                reader.db.command({'killCursors':h['collection'],'cursors':[h['cursor']]},session=h['session']);injected.append(True)
        failed=execute('cursor_failure',Limits(batch_documents=100),hook=kill)
        assert injected and failed['state']=='incompleto' and failed['error']=='cursor_lost' and not failed['complete_at_T']
        ok('cursor_fault_never_success',failed)
        old=execute('snapshot_unavailable',anchor=Timestamp(1,1))
        assert old['state']=='abortado' and old['error']=='snapshot_unavailable' and not old['complete_at_T']
        ok('snapshot_fault_never_success',old)
        def network(reader,h):raise ConnectionFailure('Synthetic network interruption; no actual infrastructure modified')
        lost=execute('network_fault',hook=network)
        assert lost['state']=='incompleto' and lost['error']=='connection_failure'
        ok('injected_network_failure',lost)
        for name,limits in [('document_budget',Limits(history_documents=100)),('batch_bytes',Limits(batch_bytes=10)),
                            ('total_bytes',Limits(total_bytes=100)),('deadline',Limits(seconds=.000001))]:
            blocked=execute(name,limits)
            assert not blocked['complete_at_T'] and not blocked['certificate_issued']
            ok(name,blocked)
        large=execute('larger_pages',Limits(batch_documents=1000))
        assert large['counts']==baseline['counts'] and large['visited']==2001 and large['duplicate_groups']==1000
        ok('larger_pages_same_T',{'visited':large['visited'],'same_counts':True})
        assert not audit.foreign and not audit.bad_snapshot and not audit.getmore_with_maxTimeMS
        result['snapshot_command_audit']={'diagnostic_roots':audit.snapshot_diagnostic_roots,'unbound_roots':audit.bad_snapshot,'getmore_with_maxTimeMS':audit.getmore_with_maxTimeMS}
        result['max_reply_bson_bytes']=dict(audit.max_reply);result['total_reply_bson_bytes']=dict(audit.reply_bytes)
        result['command_counts']={d+'.'+n:v for (d,n),v in audit.names.items()}
        result['snapshot_root_anchors']={str(k):v for k,v in audit.anchors.items()}
        result['foreign_commands']=audit.foreign
        result['indexes']={n:[i['name'] for i in db[n].list_indexes()] for n in db.list_collection_names()}
        assert all(v==['_id_'] for v in result['indexes'].values())
        result['explicit_indexes_created']=0;result['status']='passed'
        print('End-to-end validation complete; DB retained',flush=True)
    except Exception as exc:
        result['status']='failed';result['error_type']=type(exc).__name__;result['error']=str(exc)
        raise
    finally:
        setup.close();path=Path(RESULT);assert not path.exists();path.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
