"""Offline provision plan and precondition contracts; no writes or MongoDB."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import subprocess
import sys
import unittest

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId
from bson.timestamp import Timestamp
from pymongo.errors import ConnectionFailure

from backend.history_keys import derive_history_keys
from backend.history_diagnostics import Limits
from backend.history_provisioning import (
    build_plan, plan_digest, validate_intent, classify_changes, ReceiptContract, idempotency_status, reversal_status,
)
from backend.tests.test_history_diagnostics import Reader, target, row, T

RUN='8fba08ac-2f44-4d4c-bca2-c3589b13119e'


def plan(rows, **kwargs):return build_plan(Reader(rows),target(),RUN,T,**kwargs)


class ProvisioningTests(unittest.TestCase):
    def test_missing_ready_candidate_without_mutation(self):
        document=row(1);original=deepcopy(document);result=plan([document])
        self.assertTrue(result.eligible_for_review);self.assertEqual(len(result.intents),1)
        self.assertEqual(validate_intent(result,result.intents[0],document,target()),'preconditions_match')
        self.assertEqual(BSON(result.intents[0].proposed_keys).decode()['value'],derive_history_keys(document,1))
        self.assertEqual(document,original);self.assertNotIn('_history_keys',document)
        self.assertFalse(result.apply_authorized);self.assertFalse(result.revert_authorized)

    def test_absent_null_and_existing_representations(self):
        self.assertEqual(len(plan([row(1)]).intents),1)
        for value in (None,{},False,'old',{'version':1,'generation':2}):
            result=plan([row(1,_history_keys=value)])
            self.assertEqual(result.state,'blocked');self.assertFalse(result.intents)
            self.assertFalse(result.eligible_for_review)

    def test_ready_correct_is_not_modifiable(self):
        document=row(1);document['_history_keys']=derive_history_keys(document,1)
        result=plan([document]);self.assertTrue(result.eligible_for_review);self.assertFalse(result.intents)
        self.assertEqual(dict(result.counts)['ready'],1)

    def test_stale_incompatible_unverifiable(self):
        document=row(1);document['_history_keys']=derive_history_keys(document,1)
        fixtures=[dict(document,amount='71'),dict(document,_history_keys={**document['_history_keys'],'generation':2})]
        invalid=row(2,date='invalid');invalid['_history_keys']=derive_history_keys(invalid,1);fixtures.append(invalid)
        for document in fixtures:
            result=plan([document]);self.assertTrue(result.complete_at_T);self.assertEqual(result.state,'blocked')
            self.assertFalse(result.intents);self.assertFalse(result.eligible_for_review)

    def test_invalid_missing_sources_block(self):
        for changes in ({'date':'bad'},{'amount':'NaN'},{'amount':True},{'amount':{'invalid':True}}):
            result=plan([row(1,**changes)]);self.assertEqual(result.state,'blocked');self.assertFalse(result.intents)
        for changes in ({'id':None},{'user_id':'other'}):
            self.assertFalse(plan([row(1,**changes)]).complete_at_T)

    def test_duplicates_global_between_batches_and_dates(self):
        rows=[row(i,id='same',date=f'2026-10-0{i+1}') for i in range(6)]
        result=plan(rows,limits=replace(Limits(),batch_documents=2))
        self.assertEqual(result.duplicate_groups,1);self.assertEqual(result.state,'blocked');self.assertFalse(result.intents)
        # Even valid unrelated candidates are withheld when scope is ambiguous.
        result=plan(rows+[row(9)]);self.assertFalse(result.eligible_for_review);self.assertFalse(result.intents)

    def test_physical_bson_types_preserved(self):
        ids=[1,Int64(2),'s',Binary(b'one',0),Binary(b'two',1),ObjectId()]
        rows=[row(i,_id=value) for i,value in enumerate(ids)];result=plan(rows)
        self.assertEqual(len(result.intents),6)
        for intent in result.intents:
            value=BSON(intent.physical_id).decode()['value']
            document=next(r for r in rows if BSON.encode({'value':r['_id']})==intent.physical_id)
            self.assertEqual(validate_intent(result,intent,document,target()),'preconditions_match')
            self.assertEqual(BSON.encode({'value':value}),intent.physical_id)

    def test_unsupported_type_blocks(self):
        reader=Reader();reader.mutate=lambda p,r:replace(r,documents=(bytes(BSON.encode({'type':'double','count':1})),)) if p=='inventory' else r
        result=build_plan(reader,target(),RUN,T)
        self.assertFalse(result.complete_at_T);self.assertEqual(result.state,'aborted');self.assertFalse(result.intents)

    def test_changes_of_sources_and_physical_identity(self):
        document=row(1);result=plan([document]);intent=result.intents[0]
        for changes in ({'amount':'71'},{'date':'2026-10-02'},{'id':'other'},{'user_id':'other'}):
            self.assertEqual(validate_intent(result,intent,{**document,**changes},target()),'source_conflict')
            self.assertTrue(classify_changes(document,{**document,**changes})['key_sources_changed'])
        self.assertEqual(validate_intent(result,intent,{**document,'_id':Int64(1)},target()),'physical_identity_conflict')

    def test_administrative_changes_preserved_and_unknown_not_assumed_safe(self):
        document=row(1);result=plan([document]);intent=result.intents[0]
        current={**document,'notes':'Changed','name':'Changed','_reference_revision':2};before=deepcopy(current)
        self.assertEqual(validate_intent(result,intent,current,target()),'preconditions_match')
        self.assertTrue(classify_changes(document,current)['administrative_only']);self.assertEqual(current,before)
        changes=classify_changes(document,{**document,'account_id':'other'})
        self.assertTrue(changes['other_fields_changed']);self.assertFalse(changes['administrative_only'])

    def test_metadata_creation_is_a_conflict_even_if_matches(self):
        document=row(1);result=plan([document]);intent=result.intents[0]
        for value in (None,derive_history_keys(document,1)):
            self.assertEqual(validate_intent(result,intent,{**document,'_history_keys':value},target()),'metadata_conflict')

    def test_digest_deterministic_context_and_T_bound(self):
        rows=[row(1),row(2)];a=plan(rows);b=plan(list(reversed(rows)))
        self.assertEqual(a.digest,b.digest)
        for change in ({'database':'test_other'},{'generation':2},{'collection_uuid':Binary(b'x'*16,4)}):
            c=build_plan(Reader(rows),replace(target(),**change),RUN,T);self.assertNotEqual(a.digest,c.digest)
            self.assertEqual(validate_intent(a,a.intents[0],rows[0],replace(target(),**change)),'context_conflict')
        self.assertNotEqual(a.digest,build_plan(Reader(rows),target(),RUN,Timestamp(101,1)).digest)
        self.assertNotEqual(a.digest,build_plan(Reader(rows),target(),'cf929637-0c81-4dd6-a88f-456315cbe367',T).digest)

    def test_immutability_and_tampering(self):
        result=plan([row(1)])
        with self.assertRaises(FrozenInstanceError):result.state='complete'
        with self.assertRaises(FrozenInstanceError):result.intents[0].source_sha256='changed'
        self.assertFalse(replace(result,digest='changed').eligible_for_review)
        self.assertEqual(validate_intent(replace(result,digest='changed'),result.intents[0],row(1),target()),'invalid_plan')
        blocked=plan([row(1,_history_keys=None)])
        forged=replace(blocked,state='complete')
        forged=replace(forged,digest=plan_digest(forged))
        self.assertFalse(forged.eligible_for_review)
        wrong_counts=replace(result,counts=tuple((k,0) for k,_ in result.counts))
        self.assertFalse(replace(wrong_counts,digest=plan_digest(wrong_counts)).eligible_for_review)

    def test_verified_empty_plan(self):
        result=plan([]);self.assertTrue(result.complete_at_T);self.assertTrue(result.eligible_for_review)
        self.assertFalse(result.intents);self.assertFalse(result.apply_authorized)

    def test_budgets_invalidate_completeness(self):
        for limits in (replace(Limits(),history_documents=1),replace(Limits(),batch_bytes=1),
                       replace(Limits(),total_bytes=1),replace(Limits(),requests=1)):
            result=plan([row(1),row(2)],limits=limits)
            self.assertFalse(result.complete_at_T);self.assertFalse(result.intents);self.assertFalse(result.eligible_for_review)
        ticks=iter([0,0,31,32]);result=plan([],clock=lambda:next(ticks))
        self.assertFalse(result.complete_at_T);self.assertEqual(result.error,'deadline_exceeded')

    def test_incomplete_and_prior_report_cannot_authorize(self):
        reader=Reader();reader.mutate=lambda p,r:(_ for _ in ()).throw(ConnectionFailure('SECRET'))
        result=build_plan(reader,target(),RUN,T);self.assertEqual(result.state,'incomplete');self.assertFalse(result.intents)
        result=build_plan({},target(),RUN,T);self.assertFalse(result.eligible_for_review)

    def test_context_and_version_rejections(self):
        for change in ({'version':2},{'generation':0},{'user_id':'other'},{'approved':False}):
            with self.assertRaisesRegex(ValueError,'invalid_plan_context'):
                build_plan(Reader(),replace(target(),**change),RUN,T)
        with self.assertRaisesRegex(ValueError,'invalid_plan_context'):build_plan(Reader(),target(),'SECRET',T)

    def test_absent_and_null_sources_have_distinct_fingerprints(self):
        absent=row(1);absent.pop('amount');null=row(1,amount=None)
        a=plan([absent]);b=plan([null])
        self.assertNotEqual(a.intents[0].source_sha256,b.intents[0].source_sha256)
        self.assertEqual(validate_intent(a,a.intents[0],null,target()),'source_conflict')

    def test_idempotency_contracts_do_not_write(self):
        result=plan([row(1)]);intent=result.intents[0]
        record=ReceiptContract(result.run_id,result.destination_id,result.digest,intent.digest(),'confirmed')
        self.assertEqual(idempotency_status(result,intent,None),'uncertain')
        self.assertEqual(idempotency_status(result,intent,record),'original_confirmation')
        self.assertEqual(idempotency_status(result,intent,replace(record,state='uncertain')),'uncertain')
        for change in ({'run_id':'other'},{'plan_digest':'other'},{'intent_digest':'other'},{'state':'reverted'}):
            self.assertEqual(idempotency_status(result,intent,replace(record,**change)),'conflict')
        self.assertFalse(result.apply_authorized)
        self.assertEqual(idempotency_status(result,intent,{}),'conflict')

    def test_ABA_never_authorizes_reversal(self):
        original=row(1);result=plan([original]);intermediate={**original,'amount':'99'};restored=deepcopy(original)
        self.assertNotEqual(intermediate,original)
        self.assertEqual(validate_intent(result,result.intents[0],restored,target()),'preconditions_match')
        self.assertEqual(reversal_status(result,original,restored),'blocked_operational_writer_evidence_required')
        self.assertFalse(result.revert_authorized)

    def test_aggregate_report_privacy(self):
        encoded=json.dumps(plan([row(1)]).public_report())
        for value in ('synthetic-1','70.123','2026-W40','mongodb://','_history_keys','source_sha256'):
            self.assertNotIn(value,encoded)
        self.assertFalse(json.loads(encoded)['financial_correctness_asserted'])

    def test_import_without_clients_files_or_experiments(self):
        script="""
from unittest.mock import patch
import sys
with patch('pymongo.MongoClient',side_effect=AssertionError('connected')), patch('builtins.open',side_effect=AssertionError('file write')):
 import backend.history_provisioning
assert not any(n.startswith('backend.experiments') for n in sys.modules)
"""
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_digest_time_also_invalidates_completeness(self):
        from unittest.mock import patch
        import backend.history_provisioning as module
        current=[0];original=module.plan_digest
        def delayed_digest(value):
            current[0]=31;return original(value)
        with patch.object(module,'plan_digest',delayed_digest):
            result=plan([],clock=lambda:current[0])
        self.assertEqual(result.state,'aborted');self.assertFalse(result.complete_at_T)
        self.assertFalse(result.eligible_for_review);self.assertEqual(result.error,'deadline_exceeded')


if __name__=='__main__':unittest.main()
