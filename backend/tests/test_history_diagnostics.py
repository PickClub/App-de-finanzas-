"""Small BSON fixtures only; no MongoDB client or network."""
from dataclasses import replace
import json
import unittest
from uuid import UUID

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId
from bson.timestamp import Timestamp
from pymongo.errors import ConnectionFailure, OperationFailure

from backend.history_keys import derive_history_keys
from backend.history_diagnostics import (
    Target, LOCAL_URI, Limits, Response, run_diagnosis, physical_key, partition_for, bson_type, exit_code,
)

ENV='18b1080a-3bbd-47eb-88d2-b47b8c847c62'
T=Timestamp(100,1)


def target():
    return Target(LOCAL_URI,'test_offline_diagnostic','transactions',Binary(UUID(ENV).bytes,4),ENV,
                  'default-user',1,1,True)


def row(i, **changes):
    result={'_id':i,'id':f'synthetic-{i}','user_id':'default-user',
            'date':'2026-W40-4T12:00:00.123456+01:02:03','amount':'70.123456789012345678901234567890'}
    result.update(changes)
    return result


class Reader:
    def __init__(self, rows=()):
        self.rows=list(rows);self.calls=[];self.mutate=lambda phase,r:r;self.verified=0
    def reply(self,phase,req,rows,exhausted=True):
        self.calls.append((phase,req))
        return self.mutate(phase,Response(req.T,req.binding,tuple(bytes(BSON.encode(x)) for x in rows),exhausted))
    def inventory(self,req):
        counts={}
        for x in self.rows:counts[bson_type(x['_id'])]=counts.get(bson_type(x['_id']),0)+1
        return self.reply('inventory',req,[{'type':t,'count':n} for t,n in counts.items()])
    def page(self,req,part,after):
        rows=sorted([x for x in self.rows if partition_for(x['_id'])==part and
                     (after is None or physical_key(x['_id'])>physical_key(after))],key=lambda x:physical_key(x['_id']))
        return self.reply('page',req,rows[:req.batch_documents],len(rows)<=req.batch_documents)
    def duplicates(self,req):
        rows=sorted(self.rows,key=lambda x:(x['id'].encode(),physical_key(x['_id'])))
        if not rows:yield self.reply('duplicates',req,[])
        for i in range(0,len(rows),req.batch_documents):
            yield self.reply('duplicates',req,rows[i:i+req.batch_documents],i+req.batch_documents>=len(rows))
    def verify_identity(self,req):self.calls.append(('identity',req));self.verified+=1


class DiagnosticsTests(unittest.TestCase):
    def test_empty_verified_snapshot(self):
        reader=Reader();report=run_diagnosis(reader,target(),T)
        self.assertEqual(exit_code(report),0);self.assertEqual(report['visited'],0)
        self.assertTrue(report['complete_at_T']);self.assertEqual(reader.verified,1)
        self.assertTrue(all(req.T==T and req.read_concern=='snapshot' for _,req in reader.calls))
        for field in ('certificate_issued','indexed_reads_allowed','financial_correctness_asserted'):
            self.assertIs(report[field],False)

    def test_five_states_and_sources(self):
        rows=[row(i) for i in range(5)]
        for x in rows[1:]:x['_history_keys']=derive_history_keys(x,1)
        rows[2]['amount']='71';rows[3]['date']='invalid';rows[3]['_history_keys']=derive_history_keys(rows[3],1)
        rows[4]['_history_keys']['generation']=2
        report=run_diagnosis(Reader(rows),target(),T)
        self.assertEqual(set(report['counts'].values()),{1});self.assertEqual(exit_code(report),2)
        self.assertEqual(report['source_unverifiable'],1)

    def test_ready_and_historical_precision(self):
        rows=[row(1,date='20261001T120000Z'),row(2,amount=None),row(3)]
        for x in rows:x['_history_keys']=derive_history_keys(x,1)
        self.assertEqual(exit_code(run_diagnosis(Reader(rows),target(),T)),0)

    def test_bson_types_and_duplicates_across_batches_dates(self):
        ids=[1,Int64(2),'s',Binary(b'one',0),Binary(b'two',1),ObjectId()]
        rows=[row(i,_id=value,id='duplicate',date=f'2026-10-0{i+1}') for i,value in enumerate(ids)]
        report=run_diagnosis(Reader(rows),target(),T)
        self.assertEqual(report['visited'],6);self.assertEqual(report['duplicate_groups'],1)
        self.assertEqual(report['extra_duplicate_documents'],5);self.assertEqual(exit_code(report),2)
        small=[row(i,id='duplicate',date=f'2026-10-0{i+1}') for i in range(6)]
        report=run_diagnosis(Reader(small),target(),T,limits=replace(Limits(),batch_documents=2))
        self.assertEqual(report['duplicate_groups'],1);self.assertEqual(report['extra_duplicate_documents'],5)

    def test_unsupported_inventory(self):
        for typ in ('double','decimal','bool','object','array','null','date'):
            reader=Reader();reader.mutate=lambda p,r:replace(r,documents=(bytes(BSON.encode({'type':typ,'count':1})),)) if p=='inventory' else r
            self.assertEqual(run_diagnosis(reader,target(),T)['error'],'unsupported_physical_type')

    def test_target_rejections_before_read(self):
        for kwargs in ({'uri':LOCAL_URI+'secret'},{'database':'admin'},{'collection':'other'},
                       {'user_id':'other'},{'environment_id':'wrong'},{'collection_uuid':Binary(b'wrong',4)},
                       {'version':2},{'generation':0},{'approved':False}):
            reader=Reader();report=run_diagnosis(reader,replace(target(),**kwargs),T)
            self.assertEqual(exit_code(report),4);self.assertFalse(reader.calls)

    def test_time_and_binding_divergence_each_phase(self):
        for phase in ('inventory','page','duplicates'):
            for change in ({'T':Timestamp(101,1)},{'binding':'other'}):
                reader=Reader([row(1)]);reader.mutate=lambda p,r:replace(r,**change) if p==phase else r
                self.assertEqual(exit_code(run_diagnosis(reader,target(),T)),4)

    def test_cursor_snapshot_network_failure(self):
        for error,code in [(OperationFailure('private',43),3),(OperationFailure('private',239),4),
                           (OperationFailure('private',246),4),(ConnectionFailure('secret'),3)]:
            reader=Reader();reader.mutate=lambda p,r:(_ for _ in ()).throw(error)
            report=run_diagnosis(reader,target(),T);self.assertEqual(exit_code(report),code)
            self.assertNotIn('secret',json.dumps(report));self.assertNotIn('private',json.dumps(report))

    def test_limits_and_overrides(self):
        for limits in [replace(Limits(),history_documents=1),replace(Limits(),batch_bytes=1),
                       replace(Limits(),total_bytes=1),replace(Limits(),requests=1)]:
            self.assertEqual(exit_code(run_diagnosis(Reader([row(1),row(2)]),target(),T,limits=limits)),4)
        for kwargs in ({'batch_documents':101},{'batch_bytes':1048577},{'history_documents':10001},
                       {'total_bytes':33554433},{'requests':10001},{'seconds':31},{'seconds':float('nan')}):
            self.assertEqual(run_diagnosis(Reader(),target(),T,limits=replace(Limits(),**kwargs))['error'],'invalid_limits')

    def test_deadline(self):
        ticks=iter([0,31,32]);report=run_diagnosis(Reader(),target(),T,clock=lambda:next(ticks))
        self.assertEqual(report['error'],'deadline_exceeded')

    def test_no_progress_invalid_bson_and_partial_inventory(self):
        for change in ({'documents':(), 'exhausted':False},{'documents':(b'bad',)}, {'exhausted':False}):
            reader=Reader([row(1)]);reader.mutate=lambda p,r:replace(r,**change) if p=='inventory' else r
            self.assertEqual(exit_code(run_diagnosis(reader,target(),T)),4)

    def test_bad_identity_order_and_coverage(self):
        for changes in ({'id':None},{'id':1},{'user_id':'other'}):
            self.assertEqual(exit_code(run_diagnosis(Reader([row(1,**changes)]),target(),T)),4)
        reader=Reader([row(1),row(2)]);reader.mutate=lambda p,r:replace(r,documents=r.documents[::-1]) if p=='page' else r
        self.assertEqual(run_diagnosis(reader,target(),T)['error'],'unordered_or_wrong_partition')
        reader=Reader([row(1)]);reader.mutate=lambda p,r:replace(r,documents=()) if p=='duplicates' else r
        self.assertEqual(run_diagnosis(reader,target(),T)['error'],'incomplete_duplicate_coverage')

    def test_final_identity_failure_and_report_privacy(self):
        reader=Reader([row(1)]);reader.verify_identity=lambda req:(_ for _ in ()).throw(ValueError('SECRET'))
        report=run_diagnosis(reader,target(),T);self.assertEqual(exit_code(report),4)
        encoded=json.dumps(report)
        for secret in ('SECRET','synthetic-1','2026-W40','70.123','mongodb://'):
            self.assertNotIn(secret,encoded)

    def test_invalid_T(self):
        self.assertEqual(exit_code(run_diagnosis(Reader(),target(),None)),4)

    def test_empty_inventory_does_not_hide_nonempty_history(self):
        reader=Reader([row(1)]);reader.mutate=lambda p,r:replace(r,documents=()) if p=='inventory' else r
        report=run_diagnosis(reader,target(),T)
        self.assertFalse(report['complete_at_T']);self.assertEqual(exit_code(report),4)

    def test_truncated_and_unordered_duplicate_stream(self):
        for change in ({'exhausted':False},{'documents':(bytes(BSON.encode(row(2))),bytes(BSON.encode(row(1))))}):
            reader=Reader([row(1),row(2)]);reader.mutate=lambda p,r:replace(r,**change) if p=='duplicates' else r
            self.assertEqual(exit_code(run_diagnosis(reader,target(),T)),4)


if __name__=='__main__':unittest.main()
