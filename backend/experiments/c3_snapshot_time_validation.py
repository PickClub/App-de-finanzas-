"""One-shot snapshot experiment, exclusively fresh synthetic DB; never production."""
import hashlib
import json
import os
import time
import tracemalloc
from collections import Counter
from pathlib import Path

from bson import BSON
from bson.binary import Binary
from bson.decimal128 import Decimal128
from bson.int64 import Int64
from bson.objectid import ObjectId
from bson.timestamp import Timestamp
from pymongo import MongoClient, monitoring
from pymongo.errors import OperationFailure
from pymongo.write_concern import WriteConcern

from backend.financial_context import validate_metadata
from backend.history_keys import derive_history_keys, inspect_history_keys
from backend.experiments.c3_mongodb_diagnosis_design import read_filter, type_inventory_pipeline, validate_inventory, duplicate_stream_pipeline, summarize_duplicate_stream

URI='mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true'
NAME='test_c3_snapshot_9e26a10fa77a4d24985a5c963b1bba1f'
ENV='bdf679b9-ff50-46b6-a698-d7f2ca1c93d4'
RESULT='backend/experiments/results/'+NAME+'.json'
USER='default-user'


class Audit(monitoring.CommandListener):
    def __init__(self):self.foreign=[];self.commands=Counter();self.reply_bytes=Counter();self.max_reply=Counter()
    def started(self,e):
        self.commands[(e.database_name,e.command_name)]+=1
        if e.database_name!=NAME and not (e.database_name=='admin' and e.command_name in {'hello','ismaster','isMaster','buildInfo','getParameter','listDatabases','endSessions'}):
            self.foreign.append((e.database_name,e.command_name))
    def succeeded(self,e):
        size=len(BSON.encode(e.reply));self.reply_bytes[e.command_name]+=size;self.max_reply[e.command_name]=max(self.max_reply[e.command_name],size)
    def failed(self,e):pass


def resident_bytes():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])*1024


def measured(fn):
    rss=resident_bytes();start=time.perf_counter();tracemalloc.start()
    try:
        value=fn();peak=tracemalloc.get_traced_memory()[1]
        return value,{'elapsed_ms':round((time.perf_counter()-start)*1000,3),'python_peak_bytes':peak,
                      'rss_before_bytes':rss,'rss_after_bytes':resident_bytes()}
    finally:tracemalloc.stop()


def physical(i):
    k=i%6
    return (i if k==0 else Int64(i) if k==1 else f'synthetic-{i:06}' if k==2 else
            Binary(i.to_bytes(8,'big'),0 if k==3 else 1) if k in (3,4) else ObjectId(i.to_bytes(12,'big')))


def row(i):
    r={'_id':physical(i),'id':f'synthetic-logical-{i//2:06}','user_id':USER,
       'date':'2026-W40-4T12:00:00.123456+01:02:03','amount':Decimal128('70.1200')}
    state=i%5
    if state!=1:
        if state==3:r['date']='invalid-synthetic'
        r['_history_keys']=derive_history_keys(r,1)
        if state==2:r['amount']=Decimal128('71')
        if state==4:r['_history_keys']['generation']=2
    return r


def main():
    audit=Audit()
    def connect():return MongoClient(URI,serverSelectionTimeoutMS=3000,connectTimeoutMS=3000,socketTimeoutMS=15000,event_listeners=[audit])
    client=connect(); extra=None
    evidence={'database':NAME,'environment_id':ENV,'scenarios':{},'metrics':{},'certificate_issued':False}
    def ok(name,**details):
        evidence['scenarios'][name]={'passed':True,**details};print(name+': OK',flush=True)
    try:
        h=client.admin.command('hello')
        assert client.address==('127.0.0.1',27018) and h['isWritablePrimary'] and h['setName']=='app_finanzas_dev_rs'
        assert NAME not in client.list_database_names()
        assert NAME.startswith('test_c3_snapshot_')
        version=client.admin.command('buildInfo')['version'];assert version.startswith('8.0.')
        params=client.admin.command({'getParameter':1,'minSnapshotHistoryWindowInSeconds':1,'transactionLifetimeLimitSeconds':1})
        evidence['server']={'version':version,'PRIMARY':True,'replica_set':h['setName'],'sessions_minutes':h['logicalSessionTimeoutMinutes'],
                            'min_history_seconds':params['minSnapshotHistoryWindowInSeconds'],'transaction_lifetime_seconds':params['transactionLifetimeLimitSeconds']}
        db=client.get_database(NAME,write_concern=WriteConcern('majority'))
        metadata={'_id':'financial-context','version':1,'environment_id':ENV,'created_at':'2026-10-13T00:00:00Z'}
        db.moneyflow_metadata.insert_one(metadata)
        coll=db.create_collection('transactions')
        uuid=list(db.list_collections(filter={'name':'transactions'}))[0]['info']['uuid']
        evidence['collection_uuid']=bytes(uuid).hex()
        for start in range(0,6001,500):coll.insert_many([row(i) for i in range(start,min(start+500,6001))])
        def identity():
            assert client.address==('127.0.0.1',27018)
            validate_metadata(db.moneyflow_metadata.find_one({'_id':'financial-context'}),ENV)
            assert list(db.list_collections(filter={'name':'transactions'}))[0]['info']['uuid']==uuid
        identity();ok('fresh_database_identity',absent_before_first_write=True,synthetic_r6=True)
        with client.start_session(causal_consistency=False) as session:
            initial=db.command({'find':'transactions','filter':{'user_id':USER},'sort':{'_id':1},'batchSize':3,
                                'readConcern':{'level':'snapshot'},'maxTimeMS':10000},session=session)
            T=initial.get('atClusterTime') or initial['cursor'].get('atClusterTime')
            assert type(T) is Timestamp,'Server did not expose snapshot T; refuse inference from operationTime'
            cid=initial['cursor']['id']
            if cid:db.command({'killCursors':'transactions','cursors':[cid]},session=session)
        began=time.monotonic()
        evidence['T']={'seconds':T.time,'increment':T.inc,'source':'atClusterTime returned by first snapshot find'}
        ok('server_selected_T',**evidence['T'])
        def drain(database,command,session):
            reply=database.command(command,session=session)
            cursor=reply['cursor'];yield from cursor['firstBatch']
            cid=cursor['id'];namespace=cursor['ns'].split('.',1)[1]
            while cid:
                reply=database.command({'getMore':cid,'collection':namespace,'batchSize':7},session=session)
                cursor=reply['cursor'];yield from cursor['nextBatch'];cid=cursor['id']
        def read(database,command,at_time=T):
            command={**command,'readConcern':{'level':'snapshot','atClusterTime':at_time},'maxTimeMS':10000}
            with database.client.start_session(causal_consistency=False) as session:
                yield from drain(database,command,session)
        def aggregate(database,pipeline,at_time=T):
            return read(database,{'aggregate':'transactions','pipeline':pipeline,'cursor':{'batchSize':7},
                                 'allowDiskUse':False,'collation':{'locale':'simple'}},at_time)
        def walk(database,page_size):
            digest=hashlib.sha256();n=0;pages=0;states=Counter()
            for part in range(4):
                last=None
                while True:
                    identity()
                    docs=list(read(database,{'find':'transactions','filter':read_filter(USER,part,last),
                        'sort':{'_id':1},'limit':page_size,'batchSize':7,'collation':{'locale':'simple'}}))
                    if not docs:break
                    for r in docs:digest.update(BSON.encode(r));states[inspect_history_keys(r,1)]+=1;n+=1
                    last=docs[-1]['_id'];pages+=1
            return {'count':n,'digest':digest.hexdigest(),'states':dict(states),'pages':pages}
        baseline,metric=measured(lambda:walk(db,40));evidence['metrics']['baseline_pages40']=metric
        assert baseline['count']==6001
        ok('baseline_snapshot_walk',**baseline)
        inv={r['_id']:r['count'] for r in aggregate(db,type_inventory_pipeline(USER))}
        assert validate_inventory(inv)==6001
        ok('inventory_same_T',counts=inv)
        duplicates=summarize_duplicate_stream(aggregate(db,duplicate_stream_pipeline(USER)),USER)
        assert duplicates=={'visited':6001,'duplicate_groups':3000,'extra_documents':3000}
        ok('duplicates_same_T',**duplicates)
        # All changes confined to fresh synthetic DB, after T.
        coll.insert_many([{'_id':-1,'id':'synthetic-after-early','user_id':USER,'date':'2026-10-13','amount':1},
                          {'_id':ObjectId(b'\xff'*12),'id':'synthetic-after-late','user_id':USER,'date':'2026-10-13','amount':1}])
        coll.update_one({'_id':0},{'$set':{'amount':Decimal128('99')}})
        coll.delete_one({'_id':Int64(1)})
        original=list(read(db,{'find':'transactions','filter':{'_id':0},'batchSize':1}))
        deleted=list(read(db,{'find':'transactions','filter':{'_id':Int64(1)},'batchSize':1}))
        inserted=list(read(db,{'find':'transactions','filter':{'id':{'$in':['synthetic-after-early','synthetic-after-late']}},'batchSize':1}))
        assert original[0]['amount']==Decimal128('70.1200') and len(deleted)==1 and not inserted
        assert coll.find_one({'_id':0})['amount']==Decimal128('99') and coll.find_one({'_id':Int64(1)}) is None
        ok('post_T_insert_edit_delete',new_rows_hidden=True,original_value_preserved=True,deleted_row_visible_at_T=True)
        historical,metric=measured(lambda:walk(db,1000));evidence['metrics']['post_changes_pages1000']=metric
        assert historical['digest']==baseline['digest'] and historical['states']==baseline['states']
        ok('independent_walk_same_T',**historical)
        duplicate_again,metric=measured(lambda:summarize_duplicate_stream(aggregate(db,duplicate_stream_pipeline(USER)),USER))
        evidence['metrics']['duplicates_same_T']=metric;assert duplicate_again==duplicates
        live_count=coll.count_documents({'user_id':USER})
        live_duplicates=summarize_duplicate_stream(coll.aggregate(duplicate_stream_pipeline(USER),allowDiskUse=False,collation={'locale':'simple'}),USER)
        assert live_count==6002 and live_duplicates['duplicate_groups']==2999
        ok('live_comparison',snapshot_count=6001,live_count=live_count,snapshot_duplicates=3000,live_duplicates=2999)
        # Real cursor intentionally closed. No process/server crash is claimed.
        with client.start_session(causal_consistency=False) as session:
            reply=db.command({'find':'transactions','filter':read_filter(USER,0),'sort':{'_id':1},'batchSize':3,
                              'readConcern':{'level':'snapshot','atClusterTime':T}},session=session)
            last=reply['cursor']['firstBatch'][-1]['_id'];visited=len(reply['cursor']['firstBatch']);cid=reply['cursor']['id']
            assert cid
            db.command({'killCursors':'transactions','cursors':[cid]},session=session)
            try:db.command({'getMore':cid,'collection':'transactions'},session=session)
            except OperationFailure as exc:
                assert exc.code==43
                ok('killed_cursor_failure',mongo_code=exc.code)
            else:raise AssertionError('Killed cursor unexpectedly survived')
        resumed=list(read(db,{'find':'transactions','filter':read_filter(USER,0,last),'sort':{'_id':1},'batchSize':7}))
        expected=sum(inv[t] for t in ('int','long'))
        assert visited+len(resumed)==expected
        ok('new_session_resume_same_T',numeric_total=expected,same_T=True)
        extra=connect();extra_db=extra[NAME]
        recovered=list(read(extra_db,{'find':'transactions','filter':{'_id':Int64(1)},'batchSize':1}))
        assert len(recovered)==1
        ok('new_client_same_T',deleted_row_still_visible=True,physical_process_restart_tested=False)
        # Unavailable historical timestamp: no retention changes or history pressure.
        try:list(read(db,{'find':'transactions','filter':{'_id':0},'batchSize':1},Timestamp(1,1)))
        except OperationFailure as exc:
            evidence['unavailable_snapshot']={'code':exc.code,'code_name':exc.details.get('codeName'),
                'probe':'Timestamp(1,1), unavailable historical time; not natural expiry of selected T'}
            assert exc.details.get('codeName') in {'SnapshotTooOld','SnapshotUnavailable'}
            ok('unavailable_T_blocks',**evidence['unavailable_snapshot'],certificate_issued=False)
        else:raise AssertionError('Unavailable historical timestamp was unexpectedly served')
        final=list(read(db,{'find':'transactions','filter':{'_id':Int64(1)},'batchSize':1}))
        assert len(final)==1
        evidence['retention_observation']={'configured_min_seconds':params['minSnapshotHistoryWindowInSeconds'],
            'T_successfully_read_after_seconds':round(time.monotonic()-began,3),'natural_expiry_of_T_observed':False}
        ok('valid_T_still_available',**evidence['retention_observation'])
        # Metadata R6 also verified at the same time, independent current pin still valid.
        with client.start_session(causal_consistency=False) as session:
            meta=list(drain(db,{'find':'moneyflow_metadata','filter':{'_id':'financial-context'},'batchSize':1,
                          'readConcern':{'level':'snapshot','atClusterTime':T}},session))
        validate_metadata(meta[0],ENV);identity()
        ok('R6_same_T_and_current')
        indexes={n:[r['name'] for r in db[n].list_indexes()] for n in db.list_collection_names()}
        assert all(v==['_id_'] for v in indexes.values())
        assert not audit.foreign,audit.foreign
        evidence['indexes']=indexes;evidence['explicit_indexes_created']=0
        evidence['command_counts']={d+'.'+n:v for (d,n),v in audit.commands.items()}
        evidence['reply_bson_total_bytes']=dict(audit.reply_bytes);evidence['reply_bson_max_bytes']=dict(audit.max_reply)
        evidence['foreign_commands']=audit.foreign;evidence['status']='passed'
        print('Snapshot validation complete; synthetic DB retained',flush=True)
    except Exception as exc:
        evidence['status']='failed';evidence['error_type']=type(exc).__name__;evidence['error']=str(exc)
        raise
    finally:
        if extra:extra.close()
        client.close()
        path=Path(RESULT);assert not path.exists();path.write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__':main()
