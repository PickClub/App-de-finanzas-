"""Fake snapshot adapter only: no MongoClient, sessions or existing DB fixtures."""
from dataclasses import replace
from uuid import UUID
import unittest

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId
from bson.timestamp import Timestamp
from bson.decimal128 import Decimal128
from pymongo.errors import ConnectionFailure, OperationFailure

from backend.history_keys import derive_history_keys
from backend.experiments.c3_history_provision_contract import Target, Authorization, Observation
from backend.experiments.c3_history_diagnosis_offline import physical_key
from backend.experiments.c3_consistent_diagnosis_prototype import Limits, Response, StopDiagnostic, bson_type, run_diagnosis

T=Timestamp(100,7)
ENV='515dfc51-4a76-4e3f-b028-7a609a5f7103'


def row(physical, logical, **fields):
    r={'_id':physical,'id':logical,'user_id':'default-user',
       'date':'2026-W40-4T12:00:00.123456+01:02:03','amount':Decimal128('70.1200'),**fields}
    r['_history_keys']=derive_history_keys(r,1)
    return r


class FakeReader:
    def __init__(self, rows, binding):
        self.rows=tuple(BSON.encode(r) for r in rows)
        self.binding=binding;self.calls=[];self.hook=None
    def decoded(self):return [BSON(b).decode() for b in self.rows]
    def response(self,request,rows,exhausted,kind):
        self.calls.append((kind,request))
        assert request.read_concern=='snapshot' and request.T==T
        r=Response(T,self.binding,tuple(BSON.encode(x) for x in rows),exhausted)
        return self.hook(kind,r) if self.hook else r
    def inventory(self,request):
        counts={}
        for r in self.decoded():
            k=bson_type(r['_id']);counts[k]=counts.get(k,0)+1
        return self.response(request,[{'type':k,'count':v} for k,v in counts.items()],True,'inventory')
    def page(self,request,partition,after):
        rows=sorted([r for r in self.decoded() if physical_key(r['_id'])[0]-1==partition
                     and (after is None or physical_key(r['_id'])>physical_key(after))],key=lambda r:physical_key(r['_id']))
        selected=rows[:request.batch_documents]
        return self.response(request,selected,len(selected)==len(rows),'page')
    def duplicates(self,request):
        rows=sorted(self.decoded(),key=lambda r:(r['id'].encode('utf-8'),physical_key(r['_id'])))
        if not rows:
            yield self.response(request,[],True,'duplicates');return
        for start in range(0,len(rows),request.batch_documents):
            projected=[{k:r[k] for k in ('_id','id','user_id')} for r in rows[start:start+request.batch_documents]]
            yield self.response(request,projected,start+request.batch_documents>=len(rows),'duplicates')


class ConsistentPrototypeTests(unittest.TestCase):
    def setUp(self):
        target=Target('mongodb://127.0.0.1:27018/?replicaSet=synthetic','synthetic-only','transactions',Binary(UUID(ENV).bytes,4),ENV)
        self.auth=Authorization(target,'synthetic-consistent-prototype','4585e5293b7466f3a58c7faf783bd8707253d8ac',1,1,('diagnose',),approved=True)
        self.obs=Observation(target,{'_id':'financial-context','version':1,'environment_id':ENV,'created_at':'2026-10-13T00:00:00Z'})
        self.rows=[row(1,'a'),row(Int64(2),'b'),row('synthetic','c'),row(Binary(b'x',0),'d'),row(ObjectId(),'e')]
        self.reader=FakeReader(self.rows,self.auth.binding())
    def diagnose(self,reader=None,**kwargs):return run_diagnosis(reader or self.reader,self.auth,self.obs,T,**kwargs)
    def assert_failed(self,r):
        self.assertFalse(r['complete_at_T']);self.assertFalse(r['certificate_issued']);self.assertFalse(r['indexed_reads_allowed'])
        self.assertIn(r['state'],('abortado','incompleto'))
    def test_all_paths_same_snapshot_and_no_certificate(self):
        r=self.diagnose();self.assertTrue(r['complete_at_T']);self.assertTrue(r['keys_ready_at_T'])
        self.assertEqual(r['visited'],5);self.assertFalse(r['financial_correctness_asserted'])
        self.assertTrue(all(req.T==T and req.read_concern=='snapshot' for _,req in self.reader.calls))
        self.assertEqual({k for k,_ in self.reader.calls},{'inventory','page','duplicates'})
        self.assertFalse(r['certificate_issued'])
    def test_snapshot_divergence_each_phase(self):
        for phase in ('inventory','page','duplicates'):
            reader=FakeReader(self.rows,self.auth.binding())
            reader.hook=lambda kind,r,phase=phase:replace(r,T=Timestamp(101,0)) if kind==phase else r
            result=self.diagnose(reader);self.assert_failed(result)
            self.assertEqual(result['error'],'snapshot_time_mismatch')
    def test_destination_divergence(self):
        self.reader.hook=lambda k,r:replace(r,binding='other')
        r=self.diagnose();self.assert_failed(r);self.assertEqual(r['error'],'destination_mismatch')
    def test_five_states_complete_but_not_healthy(self):
        rows=[row(i,str(i)) for i in range(5)]
        del rows[0]['_history_keys'];rows[1]['amount']=Decimal128('99')
        rows[2]=row(2,'2',date='invalid-synthetic');rows[3]['_history_keys']['generation']=2
        r=self.diagnose(FakeReader(rows,self.auth.binding()))
        self.assertTrue(r['complete_at_T']);self.assertFalse(r['keys_ready_at_T'])
        self.assertEqual(r['counts'],dict.fromkeys(('missing','stale_or_corrupt','unverifiable','incompatible','ready'),1))
    def test_duplicate_groups_across_small_batches(self):
        rows=[row(i,'same' if i<3 else 'z') for i in range(4)]
        r=self.diagnose(FakeReader(rows,self.auth.binding()),limits=Limits(batch_documents=2))
        self.assertTrue(r['complete_at_T']);self.assertEqual(r['duplicate_groups'],1)
        self.assertEqual(r['extra_duplicate_documents'],2);self.assertFalse(r['keys_ready_at_T'])
    def test_missing_source_unverifiable_not_hidden(self):
        doc=row(1,'a',date='invalid-synthetic');doc.pop('_history_keys')
        r=self.diagnose(FakeReader([doc],self.auth.binding()))
        self.assertEqual(r['source_unverifiable'],1);self.assertFalse(r['keys_ready_at_T'])
    def test_cursor_loss_incomplete(self):
        def fail(kind,r):
            if kind=='page':raise OperationFailure('private contents must not leak',43)
            return r
        self.reader.hook=fail;r=self.diagnose();self.assert_failed(r);self.assertEqual(r['error'],'cursor_lost')
    def test_snapshot_loss_aborted(self):
        self.reader.hook=lambda k,r:(_ for _ in ()).throw(OperationFailure('private',239))
        r=self.diagnose();self.assert_failed(r);self.assertEqual(r['error'],'snapshot_unavailable')
    def test_connection_loss_incomplete(self):
        self.reader.hook=lambda k,r:(_ for _ in ()).throw(ConnectionFailure('private'))
        r=self.diagnose();self.assert_failed(r);self.assertEqual(r['error'],'connection_failure')
    def test_document_budget(self):
        r=self.diagnose(limits=Limits(history_documents=4));self.assert_failed(r)
        self.assertEqual(r['error'],'document_budget_exceeded')
    def test_batch_byte_budget(self):
        r=self.diagnose(limits=Limits(batch_bytes=1));self.assert_failed(r)
        self.assertEqual(r['error'],'batch_budget_exceeded')
    def test_total_byte_budget(self):
        r=self.diagnose(limits=Limits(total_bytes=1));self.assert_failed(r)
    def test_request_budget(self):
        r=self.diagnose(limits=Limits(requests=1));self.assert_failed(r)
    def test_deadline(self):
        counter=iter(range(100))
        r=self.diagnose(limits=Limits(seconds=.5),clock=lambda:next(counter))
        self.assert_failed(r);self.assertEqual(r['error'],'deadline_exceeded')
    def test_invalid_limits(self):
        for limits in (Limits(batch_documents=True),Limits(seconds=0),Limits(batch_bytes=4194305)):
            self.assert_failed(self.diagnose(limits=limits))
    def test_wrong_inventory_count_aborts(self):
        self.reader.hook=lambda k,r:replace(r,documents=(BSON.encode({'type':'int','count':99}),)) if k=='inventory' else r
        r=self.diagnose();self.assert_failed(r);self.assertEqual(r['error'],'inventory_coverage_mismatch')
    def test_unsupported_inventory_type_aborts(self):
        self.reader.hook=lambda k,r:replace(r,documents=(BSON.encode({'type':'bool','count':1}),)) if k=='inventory' else r
        self.assert_failed(self.diagnose())
    def test_inventory_not_complete_aborts(self):
        self.reader.hook=lambda k,r:replace(r,exhausted=False) if k=='inventory' else r
        self.assert_failed(self.diagnose())
    def test_no_progress_aborts(self):
        self.reader.hook=lambda k,r:replace(r,documents=(),exhausted=False) if k=='page' else r
        self.assert_failed(self.diagnose())
    def test_duplicate_stream_truncated_aborts(self):
        self.reader.duplicates=lambda req:iter(())
        r=self.diagnose();self.assert_failed(r);self.assertEqual(r['error'],'incomplete_duplicate_coverage')
    def test_duplicate_time_mismatch_after_physical_completion(self):
        self.reader.hook=lambda k,r:replace(r,T=Timestamp(102,0)) if k=='duplicates' else r
        r=self.diagnose();self.assertEqual(r['visited'],5);self.assert_failed(r)
    def test_wrong_user(self):
        r=self.diagnose(FakeReader([row(1,'a',user_id='other')],self.auth.binding()))
        self.assert_failed(r);self.assertEqual(r['error'],'invalid_identity')
    def test_invalid_bson(self):
        self.reader.hook=lambda k,r:replace(r,documents=(b'private-invalid-bson',)) if k=='page' else r
        r=self.diagnose();self.assert_failed(r);self.assertEqual(r['error'],'invalid_bson')
    def test_no_report_values_and_input_preserved(self):
        before=self.reader.rows;r=self.diagnose()
        self.assertEqual(before,self.reader.rows)
        for secret in ('70.1200','2026-W','synthetic-only',ENV):self.assertNotIn(secret,str(r))
    def test_adapter_custom_error_does_not_leak_private_text(self):
        self.reader.hook=lambda k,r:(_ for _ in ()).throw(StopDiagnostic('private-source-value'))
        result=self.diagnose();self.assert_failed(result)
        self.assertNotIn('private-source-value',str(result))

    def test_empty_snapshot(self):
        r=self.diagnose(FakeReader([],self.auth.binding()));self.assertTrue(r['complete_at_T']);self.assertEqual(r['visited'],0)
    def test_T_must_be_bson_timestamp(self):
        r=run_diagnosis(self.reader,self.auth,self.obs,100);self.assert_failed(r);self.assertEqual(r['error'],'invalid_T')
    def test_unauthorized_before_reads(self):
        r=run_diagnosis(self.reader,replace(self.auth,approved=False),self.obs,T)
        self.assert_failed(r);self.assertFalse(self.reader.calls)


if __name__=='__main__':unittest.main()
