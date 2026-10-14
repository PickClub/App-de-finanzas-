"""Fake transactions and journal in memory. Never creates MongoDB resources."""
from copy import deepcopy
from dataclasses import replace
import json
import subprocess
import sys
import unittest

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId

from backend.history_apply import (Authorization, Observation, Budgets, RunState, Evidence,
                                  Conflict, TransientTransaction, UnknownCommit, apply_plan,
                                  reconcile, evidence_for, revert_policy)
from backend.history_provisioning import build_plan
from backend.history_keys import derive_history_keys
from backend.tests.test_history_diagnostics import Reader, target, row, T

RUN='8fba08ac-2f44-4d4c-bca2-c3589b13119e'


def physical(value):return bytes(BSON.encode({'value':value}))


class FakeAdapter:
    def __init__(self, rows):
        self.rows={physical(r['_id']):deepcopy(r) for r in rows}
        self.versions={k:0 for k in self.rows}
        self.journal={};self.controller=RunState()
        self.observation=Observation(target(),'exclusive-window',True,True,True,True,0)
        self.faults=[];self.transactions=[];self.closed=0;self.cleanup_error=False
        self.before_stage=lambda tx:None
    def bind_controller(self,controller,binding):
        if controller is not self.controller:raise Conflict()
    def observe(self):return self.observation
    def receipt(self,key):return self.journal.get(key)
    def begin(self,deadline):
        tx=FakeTransaction(self,deadline);self.transactions.append(tx);return tx
    def close(self,deadline):
        assert deadline is not None
        self.closed+=1
        if self.cleanup_error:raise RuntimeError('SECRET')
    def change(self,key,**fields):
        self.rows[key].update(fields);self.versions[key]+=1


class FakeTransaction:
    def __init__(self,owner,deadline):
        self.owner=owner;self.deadline=deadline;self.closed=False;self.committed=False
        self.staged=None;self.read_version=None;self.commit_calls=0
        self.fault=owner.faults.pop(0) if owner.faults else None
    def observe(self):return self.owner.observe()
    def receipt(self,key):return self.owner.receipt(key)
    def read(self,key):
        self.key=key;self.read_version=self.owner.versions.get(key)
        return deepcopy(self.owner.rows.get(key))
    def stage(self,current,proposed,evidence):
        self.owner.before_stage(self)
        final={**BSON(current).decode(),'_history_keys':BSON(proposed).decode()['value']}
        self.staged=(current,final,evidence)
        if self.fault=='stage':raise RuntimeError('SECRET')
        if self.fault=='transient_stage':raise TransientTransaction()
    def commit(self):
        self.commit_calls+=1
        if self.committed:return
        if self.fault=='unknown_before':raise UnknownCommit()
        if self.fault=='transient_commit':raise TransientTransaction()
        current,final,evidence=self.staged
        if (self.owner.versions.get(self.key)!=self.read_version or
                BSON.encode(self.owner.rows[self.key])!=current):raise TransientTransaction()
        if evidence.key in self.owner.journal:raise TransientTransaction()
        # Publish both staged values only at the single simulated commit point.
        self.owner.rows[self.key]=final
        self.owner.versions[self.key]+=1
        self.owner.journal[evidence.key]=evidence
        self.committed=True
        if self.fault in ('unknown_after','unknown_after_always'):raise UnknownCommit()
    def close(self,deadline):
        self.closed=True
        if self.fault=='unknown_after_always' and self.committed:
            pass
        if self.owner.cleanup_error:raise RuntimeError('SECRET')


class ApplyTests(unittest.TestCase):
    def setup_case(self, rows=None):
        rows=[row(1)] if rows is None else rows
        p=build_plan(Reader(rows),target(),RUN,T)
        a=Authorization(p.run_id,p.digest,target(),p.scope,'a'*40,'exclusive-window',100,True)
        return FakeAdapter(rows),p,a
    def execute(self,adapter,p,a,**kw):
        return apply_plan(adapter,p,target(),a,adapter.controller,clock=lambda:1,**kw)
    def test_missing_ready_atomic(self):
        d,p,a=self.setup_case();before=deepcopy(d.rows)
        r=self.execute(d,p,a)
        self.assertEqual(r['state'],'confirmed');self.assertEqual(r['confirmed_documents'],1)
        self.assertEqual(len(d.journal),1)
        for key,doc in d.rows.items():
            self.assertEqual({k:v for k,v in doc.items() if k!='_history_keys'},before[key])
            self.assertEqual(doc['_history_keys'],derive_history_keys(before[key],1))
        self.assertTrue(all(t.closed for t in d.transactions));self.assertEqual(d.closed,1)
    def test_null_and_existing_blocks(self):
        for value in (None,{},derive_history_keys(row(1),1)):
            d,p,a=self.setup_case();d.rows[physical(1)]['_history_keys']=value
            self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertFalse(d.journal)
    def test_typed_physical_ids(self):
        rows=[row(i,_id=x) for i,x in enumerate((1,Int64(2),'s',Binary(b'a',1),ObjectId()))]
        d,p,a=self.setup_case(rows);self.assertEqual(self.execute(d,p,a)['confirmed_documents'],5)
        self.assertEqual({e.physical_id for e in d.journal.values()},{physical(x['_id']) for x in rows})
    def test_numeric_source_representations(self):
        for value in (Int64(70),70.0,'70'):
            d,p,a=self.setup_case([row(1,amount=70)]);d.rows[physical(1)]['amount']=value
            self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertFalse(d.journal)
    def test_physical_int64_not_int32(self):
        d,p,a=self.setup_case();d.rows[physical(1)]['_id']=Int64(1)
        self.assertEqual(self.execute(d,p,a)['state'],'blocked')
    def test_source_changes(self):
        for changes in ({'date':'2026-10-02'},{'amount':'99'},{'id':'other'},{'user_id':'other'}):
            d,p,a=self.setup_case();d.rows[physical(1)].update(changes)
            self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertFalse(d.journal)
    def test_administrative_before_read_is_preserved(self):
        d,p,a=self.setup_case();d.rows[physical(1)].update(notes='keep',name='keep')
        self.assertEqual(self.execute(d,p,a)['state'],'confirmed')
        self.assertEqual(d.rows[physical(1)]['notes'],'keep')
    def test_plan_report_and_tampering_rejected(self):
        d,p,a=self.setup_case()
        for bad in (p.public_report(),replace(p,digest='other'),replace(p,state='blocked')):
            self.assertEqual(self.execute(d,bad,a)['state'],'blocked')
        self.assertFalse(d.journal)
    def test_authorization_binding(self):
        for changes in ({'run_id':'other'},{'plan_digest':'other'},{'target':replace(target(),database='other')},
                        {'scope':'partial'},{'approved':False},{'revision':'bad'},{'expires_at':0},
                        {'exclusion_epoch':'other'}):
            d,p,a=self.setup_case();self.assertEqual(self.execute(d,p,replace(a,**changes))['state'],'blocked')
            self.assertFalse(d.transactions)
    def test_exclusion_and_uniqueness(self):
        for changes in ({'writers_excluded':False},{'ddl_excluded':False},{'metadata_stable':False},
                        {'uniqueness_complete':False},{'duplicate_groups':1},{'exclusion_epoch':'changed'}):
            d,p,a=self.setup_case();d.observation=replace(d.observation,**changes)
            self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertFalse(d.journal)
    def test_uuid_r6_and_generation_changes(self):
        for changes in ({'collection_uuid':Binary(b'x'*16,4)},{'environment_id':'cf929637-0c81-4dd6-a88f-456315cbe367'},
                        {'generation':2}):
            d,p,a=self.setup_case();d.observation=replace(d.observation,target=replace(target(),**changes))
            self.assertEqual(self.execute(d,p,a)['state'],'blocked')
    def test_duplicate_plan_rejected(self):
        d,p,a=self.setup_case([row(1,id='same'),row(2,id='same')])
        self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertFalse(d.transactions)
    def test_idempotent_same_intention(self):
        d,p,a=self.setup_case();self.execute(d,p,a);before=deepcopy(d.rows)
        r=self.execute(d,p,a);self.assertEqual(r['recovered_documents'],1)
        self.assertEqual(r['confirmed_documents'],0);self.assertEqual(d.rows,before);self.assertEqual(len(d.journal),1)
    def test_conflicting_journal(self):
        d,p,a=self.setup_case();e=evidence_for(p,p.intents[0],a)
        d.journal[e.key]=replace(e,source_sha256='other')
        self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertNotIn('_history_keys',d.rows[physical(1)])
    def test_deterministic_intent_key(self):
        d,p,a=self.setup_case();i=p.intents[0]
        self.assertEqual(evidence_for(p,i,a),evidence_for(p,i,a))
        self.assertNotEqual(evidence_for(p,i,a).key,evidence_for(replace(p,run_id='other'),i,a).key)
    def test_stage_failure_rolls_back_both(self):
        d,p,a=self.setup_case();before=deepcopy(d.rows);d.faults=['stage']
        self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertEqual(d.rows,before);self.assertFalse(d.journal)
    def test_transient_transaction_retry(self):
        for fault in ('transient_stage','transient_commit'):
            d,p,a=self.setup_case();d.faults=[fault]
            r=self.execute(d,p,a);self.assertEqual(r['state'],'confirmed')
            self.assertEqual(len(d.transactions),2);self.assertEqual(len(d.journal),1)
    def test_commit_retry_original_transaction(self):
        d,p,a=self.setup_case();d.faults=['unknown_after']
        r=self.execute(d,p,a);self.assertEqual(r['state'],'confirmed')
        self.assertEqual(len(d.transactions),1);self.assertEqual(d.transactions[0].commit_calls,2)
        self.assertEqual(len(d.journal),1)
    def test_unknown_absent_stops_and_requires_reconciliation(self):
        d,p,a=self.setup_case([row(1),row(2)]);d.faults=['unknown_before']
        r=self.execute(d,p,a);self.assertEqual(r['state'],'uncertain');self.assertFalse(d.journal)
        self.assertEqual(len(d.transactions),1)
        self.assertEqual(self.execute(d,p,a)['state'],'uncertain');self.assertEqual(len(d.transactions),1)
        rec=reconcile(d,p,target(),a,d.controller,clock=lambda:1)
        self.assertEqual(rec['state'],'uncertain');self.assertIsNotNone(d.controller.pending)
    def test_matching_receipt_reconciles_original(self):
        d,p,a=self.setup_case();d.faults=['unknown_after']
        r=self.execute(d,p,a,budgets=replace(Budgets(),commit_attempts=1));self.assertEqual(r['state'],'uncertain')
        rec=reconcile(d,p,target(),a,d.controller,clock=lambda:1)
        self.assertEqual(rec['state'],'original_confirmed');self.assertIsNone(d.controller.pending)
        self.assertEqual(self.execute(d,p,a)['recovered_documents'],1)
    def test_reconciliation_conflicting_evidence(self):
        d,p,a=self.setup_case();d.faults=['unknown_after']
        self.execute(d,p,a,budgets=replace(Budgets(),commit_attempts=1))
        key=next(iter(d.journal));d.journal[key]=replace(d.journal[key],state='other')
        self.assertEqual(reconcile(d,p,target(),a,d.controller,clock=lambda:1)['state'],'blocked')
        self.assertIsNotNone(d.controller.pending)
    def test_partial_confirmed_no_global_rollback(self):
        d,p,a=self.setup_case([row(1),row(2)]);d.faults=[None,'stage']
        r=self.execute(d,p,a);self.assertEqual(r['state'],'partial_confirmed_blocked')
        self.assertEqual(r['confirmed_documents'],1);self.assertEqual(len(d.journal),1)
        self.assertIn('_history_keys',d.rows[physical(1)]);self.assertNotIn('_history_keys',d.rows[physical(2)])
    def test_concurrent_source_change(self):
        d,p,a=self.setup_case()
        d.before_stage=lambda tx:d.change(tx.key,amount='99')
        self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertFalse(d.journal)
        self.assertEqual(d.rows[physical(1)]['amount'],'99')
    def test_loss_of_exclusion_before_commit(self):
        d,p,a=self.setup_case()
        d.before_stage=lambda tx:setattr(d,'observation',replace(d.observation,ddl_excluded=False))
        self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertFalse(d.journal)
    def test_ABA_no_revert(self):
        d,p,a=self.setup_case();original=d.rows[physical(1)]['amount']
        d.change(physical(1),amount='99');d.change(physical(1),amount=original)
        self.assertEqual(revert_policy(d,p),'blocked_operational_writer_evidence_required')
        def aba(tx):
            d.change(tx.key,amount='99');d.change(tx.key,amount=original)
        d.before_stage=aba
        self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertFalse(d.journal)
    def test_limits_and_attempts(self):
        for budgets in (replace(Budgets(),documents=1),replace(Budgets(),document_bytes=1),
                        replace(Budgets(),total_bytes=1),replace(Budgets(),transaction_attempts=0)):
            d,p,a=self.setup_case([row(1),row(2)])
            self.assertEqual(self.execute(d,p,a,budgets=budgets)['state'],'blocked');self.assertFalse(d.journal)
        d,p,a=self.setup_case();d.faults=['transient_commit']*3
        self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertEqual(len(d.transactions),3)
    def test_deadline(self):
        d,p,a=self.setup_case();ticks=iter([0,1,31,32])
        r=apply_plan(d,p,target(),a,d.controller,clock=lambda:next(ticks,32))
        self.assertEqual(r['state'],'blocked');self.assertFalse(d.journal)
    def test_cleanup_failure_blocks(self):
        d,p,a=self.setup_case();d.cleanup_error=True
        r=self.execute(d,p,a);self.assertIn('blocked',r['state']);self.assertTrue(d.controller.halted)
        self.assertTrue(all(t.closed for t in d.transactions));self.assertNotIn('SECRET',json.dumps(r))
    def test_public_report_privacy(self):
        d,p,a=self.setup_case();r=self.execute(d,p,a);encoded=json.dumps(r)
        for token in ('synthetic-1','70.123','2026-W40','physical_id','source_sha256','mongodb://','proposed_keys'):
            self.assertNotIn(token,encoded)
        self.assertFalse(r['coverage_complete_asserted']);self.assertFalse(r['indexed_reads_allowed'])
    def test_empty_plan(self):
        d,p,a=self.setup_case([]);r=self.execute(d,p,a)
        self.assertEqual(r['state'],'confirmed');self.assertEqual(r['confirmed_documents'],0)
        self.assertFalse(d.transactions)
    def test_uncertainty_cannot_be_bypassed_with_new_controller(self):
        d,p,a=self.setup_case();d.faults=['unknown_before']
        self.assertEqual(self.execute(d,p,a)['state'],'uncertain')
        r=apply_plan(d,p,target(),a,RunState(),clock=lambda:1)
        self.assertEqual(r['state'],'blocked');self.assertEqual(len(d.transactions),1)
        self.assertIsNotNone(d.controller.pending)
    def test_invalid_controller_and_unbounded_authorization(self):
        d,p,a=self.setup_case()
        self.assertEqual(apply_plan(d,p,target(),a,None,clock=lambda:1)['state'],'blocked')
        self.assertEqual(self.execute(d,p,replace(a,expires_at=float('inf')))['state'],'blocked')
        self.assertFalse(d.transactions)
    def test_uncertain_cleanup_preserves_pending(self):
        d,p,a=self.setup_case();d.cleanup_error=True;d.faults=['unknown_before']
        self.assertEqual(self.execute(d,p,a)['state'],'uncertain')
        self.assertIsNotNone(d.controller.pending);self.assertTrue(d.controller.halted)
    def test_partial_confirmed_then_uncertain(self):
        d,p,a=self.setup_case([row(1),row(2),row(3)]);d.faults=[None,'unknown_before']
        r=self.execute(d,p,a)
        self.assertEqual(r['state'],'uncertain');self.assertEqual(r['confirmed_documents'],1)
        self.assertEqual(len(d.transactions),2);self.assertEqual(len(d.journal),1)
        self.assertNotIn('_history_keys',d.rows[physical(3)])
    def test_reconciliation_cleanup_failure_does_not_clear_pending(self):
        d,p,a=self.setup_case();d.faults=['unknown_after']
        self.execute(d,p,a,budgets=replace(Budgets(),commit_attempts=1));d.cleanup_error=True
        self.assertEqual(reconcile(d,p,target(),a,d.controller,clock=lambda:1)['state'],'blocked')
        self.assertIsNotNone(d.controller.pending)

    def test_duplicate_introduced_before_commit_blocks(self):
        d,p,a=self.setup_case()
        d.before_stage=lambda tx:setattr(d,'observation',replace(d.observation,duplicate_groups=1))
        self.assertEqual(self.execute(d,p,a)['state'],'blocked');self.assertFalse(d.journal)
    def test_administrative_race_retries_fresh_document(self):
        d,p,a=self.setup_case()
        def change_once(tx):
            d.change(tx.key,notes='concurrent-note');d.before_stage=lambda tx:None
        d.before_stage=change_once
        r=self.execute(d,p,a)
        self.assertEqual(r['state'],'confirmed');self.assertEqual(len(d.transactions),2)
        self.assertEqual(d.rows[physical(1)]['notes'],'concurrent-note')
    def test_confirmed_late_commit_preserves_evidence_and_stops(self):
        d,p,a=self.setup_case();now=[1]
        original=d.begin
        def slow_begin(deadline):
            tx=original(deadline);commit=tx.commit
            def late_commit():commit();now[0]=40
            tx.commit=late_commit;return tx
        d.begin=slow_begin
        r=apply_plan(d,p,target(),a,d.controller,clock=lambda:now[0])
        self.assertEqual(r['state'],'partial_confirmed_blocked')
        self.assertEqual(r['confirmed_documents'],1);self.assertEqual(len(d.journal),1)
    def test_reconciliation_wrong_context_keeps_pending(self):
        d,p,a=self.setup_case();d.faults=['unknown_before'];self.execute(d,p,a)
        wrong=replace(target(),database='other')
        self.assertEqual(reconcile(d,p,wrong,a,d.controller,clock=lambda:1)['state'],'blocked')
        self.assertIsNotNone(d.controller.pending)

    def test_import_no_effects(self):
        script="""
from unittest.mock import patch
import sys
with patch('pymongo.MongoClient',side_effect=AssertionError('connection')),patch('builtins.open',side_effect=AssertionError('file')):
 import backend.history_apply
assert not any(n.startswith('backend.experiments') for n in sys.modules)
"""
        r=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)


if __name__=='__main__':unittest.main()
