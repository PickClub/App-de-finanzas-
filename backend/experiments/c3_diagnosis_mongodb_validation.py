"""Explicit one-shot synthetic validation. Not a production diagnostic adapter.

No imported server, .env, index creation, migrations, cleanup or other DB data.
Only admin identity reads and a pinned absent synthetic DB are used.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import time
import tracemalloc
from dataclasses import replace
from collections import Counter

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId
from bson.decimal128 import Decimal128
from pymongo import MongoClient, monitoring
from pymongo.errors import OperationFailure

from backend.financial_context import validate_metadata
from backend.history_keys import derive_history_keys, inspect_history_keys
from backend.experiments.c3_history_provision_contract import Target, Authorization, Observation, Conflict
from backend.experiments.c3_history_diagnosis_offline import physical_key, typed_id
from backend.experiments.c3_mongodb_diagnosis_design import (
    CheckpointAuthority, duplicate_stream_pipeline, pack_bounded,
    read_filter, summarize_duplicate_stream, type_inventory_pipeline, validate_inventory,
)

URI = 'mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true'
DATABASE = 'test_c3_diagnosis_real_bb84944e2f57492191f0081ee055cf3f'
ENVIRONMENT = 'ef787808-ba5d-459d-9a90-6931f2467b2b'
RESULT = 'backend/experiments/results/' + DATABASE + '.json'
USER = 'default-user'
ADMIN = {'hello', 'ismaster', 'isMaster', 'buildInfo', 'listDatabases', 'endSessions'}


class Audit(monitoring.CommandListener):
    def __init__(self):
        self.names = Counter()
        self.violations = []
        self.replies = []
    def started(self, event):
        self.names[(event.database_name, event.command_name)] += 1
        if event.database_name != DATABASE and not (event.database_name == 'admin' and event.command_name in ADMIN):
            self.violations.append((event.database_name, event.command_name))
    def succeeded(self, event):
        self.replies.append((event.command_name, event.duration_micros, len(BSON.encode(event.reply))))
    def failed(self, event):
        pass


def timed(function):
    tracemalloc.start()
    start = time.perf_counter()
    try:
        result = function()
        _, peak = tracemalloc.get_traced_memory()
        return result, {'wall_ms': round((time.perf_counter()-start)*1000, 3),
                        'python_tracemalloc_peak_bytes': peak,
                        'process_lifetime_maxrss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    finally:
        tracemalloc.stop()


def physical(i):
    kind = i % 6
    if kind == 0: return i
    if kind == 1: return Int64(i)
    if kind == 2: return f'synthetic-physical-{i:06}'
    if kind == 3: return Binary(i.to_bytes(8, 'big'), 0)
    if kind == 4: return Binary(i.to_bytes(8, 'big'), 1)
    return ObjectId(i.to_bytes(12, 'big'))


def row(i):
    return {'_id': physical(i), 'id': f'synthetic-logical-{i//2:06}', 'user_id': USER,
            'date': '20261001T120000.123456Z', 'amount': Decimal128('70.1200'), 'serial': i}


def summarize_explain(value, path=''):
    keys = {'executionTimeMillis','nReturned','totalDocsExamined','totalKeysExamined','usedDisk','spills',
            'totalDataSizeSorted','totalDataSizeSortedBytesEstimate','memUsage','memLimit','memoryUsageBytesEstimate'}
    out = {}
    if isinstance(value, dict):
        for k,v in value.items():
            p = path+'.'+k
            if k in keys and isinstance(v, (int,float,bool)):
                out[p] = v
            elif isinstance(v, (dict,list)):
                out.update(summarize_explain(v,p))
    elif isinstance(value,list):
        for i,v in enumerate(value):out.update(summarize_explain(v,path+f'[{i}]'))
    return out


def main():
    audit = Audit()
    # Short identity selection; bounded 30s socket to avoid hanging synthetic scans.
    client = MongoClient(URI, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000,
                         socketTimeoutMS=30000, event_listeners=[audit])
    result = {'database': DATABASE, 'environment_id': ENVIRONMENT, 'scenarios': {}, 'metrics': {}}
    def passed(name, details):
        result['scenarios'][name] = {'passed': True, **details}
        print(name + ': OK', flush=True)
    try:
        hello = client.admin.command('hello')
        assert hello['setName']=='app_finanzas_dev_rs' and hello['isWritablePrimary'] is True
        assert hello.get('logicalSessionTimeoutMinutes') is not None
        assert client.address==('127.0.0.1',27018)
        assert DATABASE not in client.list_database_names(), 'Synthetic database already exists; refusing all writes'
        assert DATABASE.startswith('test_c3_diagnosis_real_')
        result['server'] = {'address':list(client.address),'setName':hello['setName'], 'PRIMARY':True,
                            'version':client.admin.command('buildInfo')['version']}
        database = client[DATABASE]
        # First writes, exclusively after absent-database and local PRIMARY checks.
        metadata = {'_id':'financial-context','version':1,'environment_id':ENVIRONMENT,
                    'created_at':'2026-10-13T00:00:00+00:00'}
        database.moneyflow_metadata.insert_one(metadata)
        collection = database.create_collection('transactions')
        collection_uuid = list(database.list_collections(filter={'name':'transactions'}))[0]['info']['uuid']
        target = Target(URI, DATABASE, 'transactions', collection_uuid, ENVIRONMENT)
        auth = Authorization(target,'synthetic-real-validation','4585e5293b7466f3a58c7faf783bd8707253d8ac',
                             1,1,('diagnose',),approved=True)
        obs = Observation(target,metadata)
        def guard():
            assert client.address==('127.0.0.1',27018)
            h=client.admin.command('hello')
            assert h['isWritablePrimary'] and h['setName']=='app_finanzas_dev_rs'
            current=database.moneyflow_metadata.find_one({'_id':'financial-context'})
            validate_metadata(current,ENVIRONMENT)
            uuid=list(database.list_collections(filter={'name':'transactions'}))[0]['info']['uuid']
            assert uuid==collection_uuid
            auth.check('diagnose',replace(obs,r6_metadata=current))
        guard()
        result['collection_uuid'] = bytes(collection_uuid).hex()
        passed('isolation_r6_uuid',{'existing_database_data_accessed':False})
        print('Preparing 100001 synthetic documents in bounded insert batches',flush=True)
        for start in range(0,100001,1000):
            collection.insert_many([row(i) for i in range(start,min(start+1000,100001))])
        inventory={r['_id']:r['count'] for r in collection.aggregate(type_inventory_pipeline(USER),allowDiskUse=False)}
        assert validate_inventory(inventory)==100001
        passed('type_inventory',{'counts':inventory})
        reference=hashlib.sha256()
        for r in collection.find({'user_id':USER},{'_id':1}).sort('_id',1).collation({'locale':'simple'}).batch_size(1000):
            reference.update(BSON.encode({'_id':r['_id']}))
        def walk(limit, serial_limit=None, validate_keys=False):
            digest=hashlib.sha256(); count=0; max_reply=0; statuses=Counter(); pages=0
            authority=CheckpointAuthority(os.urandom(32)); final=None
            for part in range(4):
                last=None
                while True:
                    guard()
                    query=read_filter(USER,part,last)
                    if serial_limit is not None: query['serial']={'$lt':serial_limit}
                    rows=list(collection.find(query).sort('_id',1).collation({'locale':'simple'}).limit(limit).batch_size(limit))
                    for encoded_batch in pack_bounded((BSON.encode(r) for r in rows),limit,1048576):
                        max_reply=max(max_reply,sum(map(len,encoded_batch)))
                    if not rows:
                        final=authority.issue(auth,obs,partition=part,last_id=last,visited=count,exhausted=True)
                        break
                    for r in rows:
                        if last is not None:assert physical_key(r['_id'])>physical_key(last)
                        last=typed_id(r['_id']);digest.update(BSON.encode({'_id':r['_id']})); count+=1
                        if validate_keys:statuses[inspect_history_keys(r,1)]+=1
                    final=authority.issue(auth,obs,partition=part,last_id=last,visited=count)
                    assert authority.accept(auth,obs,final)['visited']==count
                    pages+=1
            return {'count':count,'digest':digest.hexdigest(),'pages':pages,'max_processing_batch_bson_bytes':max_reply,
                    'statuses':dict(statuses),'checkpoint_sequence':authority.accept(auth,obs,final)['sequence']}
        outcome,metrics=timed(lambda:walk(1000,validate_keys=True))
        assert outcome['count']==100001 and outcome['digest']==reference.hexdigest()
        assert outcome['statuses']=={'missing':100001}
        passed('partition_walk_complete',outcome);result['metrics']['walk_100001']=metrics
        # Small and large page sizes on known bounded synthetic subsets, not scope certificates.
        for n,limit in ((501,5),(2001,100),(10001,1000),(50001,1000)):
            outcome,metrics=timed(lambda n=n,limit=limit:walk(limit,n))
            assert outcome['count']==n
            passed(f'page_size_{n}_{limit}',{'count':n,'pages':outcome['pages']})
            result['metrics'][f'walk_subset_{n}']={**metrics,'scope':'benchmark_serial_subset','page_limit':limit}
        # Read-only stream duplicate check: two equal logical IDs per pair.
        guard()
        duplicate,metrics=timed(lambda:summarize_duplicate_stream(collection.aggregate(
            duplicate_stream_pipeline(USER),allowDiskUse=False,collation={'locale':'simple'},batchSize=1000,maxTimeMS=15000),USER))
        assert duplicate=={'visited':100001,'duplicate_groups':50000,'extra_documents':50000}
        passed('duplicates_stream',duplicate);result['metrics']['duplicates_100001']=metrics
        explanation=database.command('explain',{'aggregate':'transactions','pipeline':duplicate_stream_pipeline(USER),
            'cursor':{},'allowDiskUse':False,'collation':{'locale':'simple'},'maxTimeMS':15000},verbosity='executionStats')
        result['sort_explain']=summarize_explain(explanation)
        assert not any(v is True for k,v in result['sort_explain'].items() if k.endswith('usedDisk'))
        passed('sort_no_disk_spill',{'explain':result['sort_explain']})
        # HMAC, replay, context and session loss, using the real pinned collection scope.
        signer=CheckpointAuthority(os.urandom(32))
        token=signer.issue(auth,obs,partition=0,last_id=0,visited=1)
        invalid=[]
        for kind, fn in (
            ('tampered',lambda:signer.accept(auth,obs,token[:-1]+bytes([token[-1]^1]))),
            ('other_context',lambda:signer.accept(replace(auth,generation=2),obs,token)),
            ('wrong_uuid',lambda:signer.accept(auth,replace(obs,target=replace(target,collection_uuid=Binary(os.urandom(16),4))),token))):
            try:fn()
            except (Conflict,ValueError):invalid.append(kind)
        assert len(invalid)==3
        newer=signer.issue(auth,obs,partition=0,last_id=6,visited=2)
        try:signer.accept(auth,obs,token)
        except Conflict:invalid.append('old_sequence')
        assert len(invalid)==4 and signer.accept(auth,obs,newer)['last_id']==6
        passed('hmac_context_sequence',{'rejections':invalid})
        # Foreign namespace access is never attempted; changed pin fails before a read.
        try:auth.check('diagnose',replace(obs,target=replace(target,database='other')))
        except Conflict:passed('wrong_destination_blocked',{'query_sent':False})
        edge=database.create_collection('edge_cases')
        edge_rows=[]
        for i,state in enumerate(('missing','ready','stale_or_corrupt','unverifiable','incompatible')):
            r=row(i)
            if state!='missing':
                if state=='unverifiable':r['date']='invalid-synthetic'
                r['_history_keys']=derive_history_keys(r,1)
                if state=='stale_or_corrupt':r['amount']=Decimal128('71')
                if state=='incompatible':r['_history_keys']['generation']=2
            edge_rows.append(r)
        edge.insert_many(edge_rows)
        before=hashlib.sha256(b''.join(BSON.encode(r) for r in edge.find().sort('_id',1))).hexdigest()
        states=Counter(inspect_history_keys(r,1) for r in edge.find())
        assert states==Counter({'missing':1,'ready':1,'stale_or_corrupt':1,'unverifiable':1,'incompatible':1})
        after=hashlib.sha256(b''.join(BSON.encode(r) for r in edge.find().sort('_id',1))).hexdigest()
        assert before==after
        passed('classification_read_only',{'states':dict(states),'documents_unchanged':True})
        unsupported=database.create_collection('unsupported')
        unsupported.insert_many([{'_id':False,'id':'synthetic-bool','user_id':USER},
                                  {'_id':3.25,'id':'synthetic-double','user_id':USER}])
        types={r['_id']:r['count'] for r in unsupported.aggregate(type_inventory_pipeline(USER),allowDiskUse=False)}
        try:validate_inventory(types)
        except Conflict:passed('unsupported_types_block',{'types':types,'repairs':0})
        # Live dataset changed between pages, only synthetic writes in this DB.
        live=database.create_collection('live')
        live.insert_many([{'_id':2,'user_id':USER,'id':'synthetic-old','amount':1},
                          {'_id':'a','user_id':USER,'id':'synthetic-string','amount':1}])
        first=list(live.find(read_filter(USER,0)).sort('_id',1).limit(1))
        live.insert_one({'_id':1,'user_id':USER,'id':'synthetic-late','amount':1})
        live.update_one({'_id':2},{'$set':{'amount':2}})
        remaining=list(live.find(read_filter(USER,0,first[0]['_id'])))
        assert not remaining and live.count_documents({'user_id':USER})==3
        passed('live_insert_edit_limitation',{'late_insert_omitted':True,'visited_amount_now_changed':True,'certified':False})
        # Interrupted run with issued checkpoint; retry same successor query without extra writes.
        signer=CheckpointAuthority(os.urandom(32)); token=signer.issue(auth,obs,partition=0,last_id=0,visited=1)
        count_a=collection.count_documents(read_filter(USER,0,signer.accept(auth,obs,token)['last_id']))
        try:raise RuntimeError('synthetic interruption after returned checkpoint')
        except RuntimeError:pass
        count_b=collection.count_documents(read_filter(USER,0,signer.accept(auth,obs,token)['last_id']))
        assert count_a==count_b
        passed('partial_failure_resume',{'same_successor_count':count_b,'new_writes':0})
        try:list(pack_bounded([BSON.encode({'_id':1,'padding':'x'*5000})],1,1000))
        except Conflict:passed('client_oversize_block',{'repair_writes':0})
        # Negative resource probe. Deliberately exceed server sort memory with spill forbidden.
        heavy=database.create_collection('resource_probe')
        for start in range(0,30000,1000):
            heavy.insert_many([{'_id':i,'padding':f'{30000-i:06}'+('x'*4096)} for i in range(start,start+1000)])
        started=time.perf_counter()
        try:
            list(heavy.aggregate([{'$sort':{'padding':1,'_id':1}}],allowDiskUse=False,maxTimeMS=15000,batchSize=1))
        except OperationFailure as exc:
            assert exc.code in (292,16819), (exc.code,'Unexpected resource failure')
            passed('server_sort_resource_limit',{'mongo_code':exc.code,'disk_spill_allowed':False,
                                                'wall_ms':round((time.perf_counter()-started)*1000,3)})
        else:
            passed('server_sort_resource_limit',{'limit_not_reached':True,'disk_spill_allowed':False})
        indexes={name:[d['name'] for d in database[name].list_indexes()] for name in database.list_collection_names()}
        assert all(names==['_id_'] for names in indexes.values())
        result['indexes']=indexes; result['explicit_indexes_created']=0
        assert not audit.violations,audit.violations
        result['command_audit']={db+'.'+name:n for (db,name),n in audit.names.items()}
        result['reply_metrics']={name:{'count':len([x for x in audit.replies if x[0]==name]),
            'max_bson_reply_bytes':max(x[2] for x in audit.replies if x[0]==name)} for name in {'find','getMore','aggregate'} if any(x[0]==name for x in audit.replies)}
        result['foreign_namespace_commands']=audit.violations
        result['status']='passed'
        print('Validation completed; synthetic DB retained',flush=True)
    except Exception as exc:
        result['status']='failed'; result['failure_type']=type(exc).__name__; result['failure']=str(exc)
        raise
    finally:
        client.close()
        # Synthetic aggregate metrics only. Never output financial records/tokens/credentials.
        path=Path(RESULT)
        assert not path.exists()
        path.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
