"""Offline lab profile tests. Only BSON fixtures and fake clients."""
from dataclasses import replace
from copy import deepcopy
import json
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from bson import BSON
from bson.binary import Binary

from backend.history_apply_lab import *
from backend.history_diagnostics import Target
from backend.history_apply import Authorization, RunState, apply_plan, Conflict
from backend.history_apply_mongodb import SyntheticPermit, SyntheticMongoApplyAdapter, JOURNAL, MARKER
from backend.history_provisioning import build_plan
from backend.tests.test_history_diagnostics import Reader, row, T, ENV
from backend.tests.test_history_apply_mongodb_adapter import Client, Verifier, RUN
from backend.tests.history_apply_synthetic_runner import (
    lab_connection_spec, request_mongodb_execution, ExternalExclusionVerifier, RunnerBlocked,
)


def target():
    return LabTarget(Binary(b't'*16, 4), Binary(b'j'*16, 4), Binary(b'm'*16, 4),
                     ENV, 1, True, True)


class LabClient(Client):
    address = LAB_ADDRESS
    def __init__(self, rows, t):
        super().__init__(rows, t)
        self.replica = LAB_REPLICA
        self.auth_user = LAB_USER
        self.auth_role = 'c3_apply_limited'
        self.uuids['moneyflow_metadata'] = t.metadata_uuid
        self.moneyflow_metadata = self['moneyflow_metadata']
        self.docs['moneyflow_metadata'][1].update(nonce=LAB_NONCE,
            journal_uuid=t.journal_uuid, metadata_uuid=t.metadata_uuid)
    def __getitem__(self, name):
        if name == LAB_DATABASE:
            return self
        return super().__getitem__(name)
    def command(self, command):
        if type(command) is dict:
            self.calls.append(('connectionStatus', 'admin', {}, None))
            return {'authInfo': {'authenticatedUsers': [{'user': self.auth_user, 'db': 'admin'}],
                'authenticatedUserRoles': [{'role': self.auth_role, 'db': 'admin'}]}}
        return super().command(command)


def case(verifier=None):
    t = target()
    rows = [row(1)]
    plan = build_plan(Reader(rows), t, RUN, T)
    auth = Authorization(RUN, plan.digest, t, plan.scope, 'b'*40,
                         'external-epoch', time.monotonic()+60, True)
    permit = SyntheticPermit(auth, LAB_NONCE, t.journal_uuid, True, True)
    client = LabClient(rows, t)
    adapter = SyntheticMongoApplyAdapter(client, plan, permit, verifier or Verifier(t))
    return client, plan, auth, permit, adapter


class LabTests(unittest.TestCase):
    def test_closed_target(self): target().validate()
    def test_development_uri_rejected(self):
        with self.assertRaises(StopDiagnostic): replace(target(), uri='mongodb://127.0.0.1:27018/').validate()
    def test_other_database_rejected(self):
        with self.assertRaises(StopDiagnostic): replace(target(), database='test_other').validate()
    def test_other_replica_rejected(self):
        with self.assertRaises(StopDiagnostic): replace(target(), replica='app_finanzas_dev_rs').validate()
    def test_other_host_rejected(self):
        with self.assertRaises(StopDiagnostic): replace(target(), uri=LAB_URI.replace('127.0.0.1','localhost')).validate()
    def test_nonce_exact(self):
        with self.assertRaises(StopDiagnostic): replace(target(), nonce='a'*32).validate()
    def test_admin_profile_rejected(self):
        with self.assertRaises(StopDiagnostic): replace(target(), auth_user='c3_admin').validate()
    def test_wrong_mechanism(self):
        with self.assertRaises(StopDiagnostic): replace(target(), mechanism='SCRAM-SHA-1').validate()
    def test_uuid_type_rejected(self):
        for bad in ('uuid', b't'*16, Binary(b't'*16,0), Binary(b't',4)):
            with self.subTest(bad=type(bad)), self.assertRaises(StopDiagnostic):
                replace(target(), collection_uuid=bad).validate()
    def test_unapproved_physical_pins_rejected(self):
        with self.assertRaises(StopDiagnostic): replace(target(), physical_pins_approved=False).validate()
    def test_same_uuid_for_two_collections_rejected(self):
        with self.assertRaises(StopDiagnostic): replace(target(), metadata_uuid=target().collection_uuid).validate()
    def test_binding_deterministic_and_sensitive_to_pins(self):
        self.assertEqual(target().binding(), target().binding())
        for change in ({'metadata_uuid':Binary(b'n'*16,4)}, {'journal_uuid':Binary(b'k'*16,4)},
                       {'generation':2}, {'environment_id':'51f6339c-9659-46a4-bbac-2f358428f5fb'}):
            self.assertNotEqual(target().binding(), replace(target(), **change).binding())
    def test_plan_digest_bound_to_profile(self):
        p=build_plan(Reader([row(1)]),target(),RUN,T)
        q=build_plan(Reader([row(1)]),replace(target(),generation=2),RUN,T)
        self.assertNotEqual(p.digest,q.digest)
    def test_options_pure_no_client(self):
        with patch('pymongo.MongoClient',side_effect=AssertionError('network')):
            options=lab_connection_spec(target(),LabCredentials('PRIVATE_SECRET'))
        self.assertEqual(options['host'],LAB_URI)
        self.assertFalse(options['retryWrites']);self.assertFalse(options['retryReads'])
        self.assertFalse(options['connect']);self.assertEqual(options['maxPoolSize'],1)
    def test_credentials_admin_rejected_and_private_repr(self):
        self.assertNotIn('PRIVATE_SECRET',repr(LabCredentials('PRIVATE_SECRET')))
        with self.assertRaises(RunnerBlocked) as error:
            lab_connection_spec(target(),LabCredentials('PRIVATE_SECRET',username='c3_admin'))
        self.assertNotIn('PRIVATE_SECRET',str(error.exception))
    def test_development_type_rejected_by_runner(self):
        with self.assertRaises(RunnerBlocked):lab_connection_spec(object(),LabCredentials('PRIVATE_SECRET'))
    def test_gate_never_loads_credentials_or_connects(self):
        with patch('pymongo.MongoClient',side_effect=AssertionError('network')), \
                patch('backend.history_apply_lab.load_lab_credentials',side_effect=AssertionError('files')):
            result=request_mongodb_execution(target(),LabCredentials('PRIVATE_SECRET'))
        self.assertFalse(result['connection_attempted'])
        self.assertEqual(result['error'],'external_exclusion_unproven')
        self.assertNotIn('PRIVATE_SECRET',json.dumps(result))
    def test_missing_exclusion_blocks_before_writes(self):
        c,p,a,permit,adapter=case(ExternalExclusionVerifier())
        result=apply_plan(adapter,p,a.target,a,RunState())
        self.assertEqual(result['confirmed_documents'],0)
        self.assertFalse(any(op in ('insert','update') for op,*_ in c.calls))
    def test_offline_atomic_and_public_report(self):
        c,p,a,permit,adapter=case()
        before=deepcopy(c.docs['transactions'])
        report=apply_plan(adapter,p,a.target,a,RunState())
        self.assertEqual(report['confirmed_documents'],1)
        self.assertEqual(before,[{k:v for k,v in d.items() if k!='_history_keys'} for d in c.docs['transactions']])
        self.assertFalse(report['operational_apply_authorized'])
    def test_metadata_uuid_change_blocks(self):
        c,p,a,permit,adapter=case();c.uuids['moneyflow_metadata']=Binary(b'x'*16,4)
        report=apply_plan(adapter,p,a.target,a,RunState())
        self.assertEqual(report['confirmed_documents'],0)
        self.assertFalse(any(op in ('insert','update') for op,*_ in c.calls))
    def test_wrong_authenticated_user_blocks(self):
        c,p,a,permit,adapter=case();c.auth_user='c3_admin'
        self.assertEqual(apply_plan(adapter,p,a.target,a,RunState())['confirmed_documents'],0)
    def test_development_address_blocks(self):
        c,p,a,permit,adapter=case();c.address=('127.0.0.1',27018)
        self.assertEqual(apply_plan(adapter,p,a.target,a,RunState())['confirmed_documents'],0)
    def test_uncertain_commit_stops_more_documents(self):
        from backend.history_apply import Budgets
        c,p,a,permit,adapter=case();c.commit_errors=['after']
        report=apply_plan(adapter,p,a.target,a,RunState(),budgets=Budgets(commit_attempts=1))
        self.assertEqual(report['state'],'uncertain')
        self.assertEqual(len(c.sessions),1)
    def test_lab_reader_reuses_traversal(self):
        self.assertTrue(issubclass(LabSnapshotReader,MongoSnapshotReader))
        with self.assertRaises(StopDiagnostic):LabSnapshotReader(object(),object())
    def test_lab_reader_checks_three_physical_pins(self):
        c,p,a,permit,adapter=case()
        reader=LabSnapshotReader(c,a.target)
        reader._identity_current(time.monotonic()+5)
        self.assertEqual(c.info_closed,3)
        c.uuids['moneyflow_metadata']=Binary(b'z'*16,4)
        with self.assertRaises(StopDiagnostic):reader._identity_current(time.monotonic()+5)
    def test_replica_mismatch_before_writes(self):
        c,p,a,permit,adapter=case();c.replica='app_finanzas_dev_rs'
        self.assertEqual(apply_plan(adapter,p,a.target,a,RunState())['confirmed_documents'],0)
        self.assertFalse(any(op in ('insert','update') for op,*_ in c.calls))
    def test_permit_uuid_and_nonce_mismatch(self):
        c,p,a,permit,adapter=case()
        for change in ({'nonce':'a'*32},{'journal_uuid':Binary(b'z'*16,4)}):
            with self.assertRaises(Conflict):SyntheticMongoApplyAdapter(c,p,replace(permit,**change),Verifier(a.target))
    def test_credentials_file_error_sanitized(self):
        with patch.object(Path,'is_symlink',return_value=False), \
                patch.object(Path,'stat',return_value=type('S',(),{'st_mode':0o40700})()), \
                patch('os.open',side_effect=OSError('PRIVATE_SECRET')):
            with self.assertRaises(StopDiagnostic) as error:load_lab_credentials()
        self.assertEqual(str(error.exception),'private_credentials_unavailable')
        self.assertNotIn('PRIVATE_SECRET',str(error.exception))
    def test_auth_role_mismatch_blocks(self):
        c,p,a,permit,adapter=case();c.auth_role='root'
        self.assertEqual(apply_plan(adapter,p,a.target,a,RunState())['confirmed_documents'],0)
    def test_metadata_marker_pin_mismatch_blocks(self):
        c,p,a,permit,adapter=case()
        c.docs['moneyflow_metadata'][1]['metadata_uuid']=Binary(b'z'*16,4)
        self.assertEqual(apply_plan(adapter,p,a.target,a,RunState())['confirmed_documents'],0)
    def test_import_no_io(self):
        script='''
from unittest.mock import patch
with patch('pymongo.MongoClient',side_effect=AssertionError('network')), patch('builtins.open',side_effect=AssertionError('files')):
 import backend.history_apply_lab
 import backend.history_apply_mongodb
 import backend.tests.history_apply_synthetic_runner
'''
        r=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)


from backend.tests.test_history_diagnose_cli import Client as SnapshotClient, CommandCursor as FakeCursor


def observer_target():
    t=target()
    return LabObserverTarget(t.collection_uuid,t.journal_uuid,t.metadata_uuid,ENV,1)


class ObserverClient(SnapshotClient):
    address=LAB_ADDRESS
    def __init__(self,rows=()):
        super().__init__(rows)
        self.replica=LAB_REPLICA
        self.auth_user='c3_observer';self.auth_role='c3_observer_limited'
        t=observer_target()
        self.pins={'transactions':t.collection_uuid,JOURNAL:t.journal_uuid,'moneyflow_metadata':t.metadata_uuid}
    def list_collections(self,filter,session=None):
        self.calls.append(('listCollections',filter,session))
        client=self
        class Info:
            def __enter__(self):return self
            def __exit__(self,*args):client.info_closed+=1
            def __iter__(self):return iter([{'info':{'uuid':client.pins[filter['name']]}}])
        return Info()
    def command(self,command,session=None):
        if type(command) is dict and 'connectionStatus' in command:
            self.calls.append(('connectionStatus',command,session))
            return {'authInfo':{'authenticatedUsers':[{'user':self.auth_user,'db':'admin'}],
                    'authenticatedUserRoles':[{'role':self.auth_role,'db':'admin'}]}}
        reply=super().command(command,session=session)
        if 'cursor' in reply:
            name=command.get('find',command.get('aggregate'))
            reply['cursor']['ns']=LAB_DATABASE+'.'+name
        return reply


class ObserverPlanTests(unittest.TestCase):
    def run_plan(self,client=None,target=None,**kwargs):
        client=ObserverClient([row(1),row(2)]) if client is None else client
        with patch('pymongo.command_cursor.CommandCursor',FakeCursor):
            result=build_observer_plan(client,observer_target() if target is None else target,RUN,**kwargs)
        return client,result
    def test_observer_complete_candidate_plan_one_session(self):
        c,e=self.run_plan();r=e.public_report()
        self.assertTrue(r['complete_at_T']);self.assertEqual(r['candidate_count'],2)
        self.assertFalse(r['pins_approved']);self.assertFalse(r['apply_authorized'])
        self.assertFalse(r['writer_exclusion_asserted'])
        self.assertFalse(hasattr(observer_target(),'approved'))
        self.assertFalse(hasattr(observer_target(),'physical_pins_approved'))
        self.assertEqual(len(c.sessions),1);self.assertTrue(c.sessions[0].ended)
        self.assertTrue(c.closed)
        self.assertEqual(e.metrics['sessions_opened'],1);self.assertEqual(e.metrics['sessions_closed'],1)
        self.assertTrue(all(s is c.sessions[0] for _,_,s in c.calls))
        concern=[cmd['readConcern'] for _,cmd,_ in c.calls if 'readConcern' in cmd]
        self.assertEqual(sum('atClusterTime' not in rc for rc in concern),1)
        self.assertTrue(all(rc['level']=='snapshot' for rc in concern))
        self.assertEqual({rc['atClusterTime'] for rc in concern if 'atClusterTime' in rc},{T})
        self.assertTrue(all(op in ('hello','buildInfo','connectionStatus','listCollections','find','aggregate','killCursors') for op,*_ in c.calls))
    def test_apply_and_administrative_accounts_rejected(self):
        for user,role in [('c3_apply','c3_apply_limited'),('c3_admin','root'),('c3_recovery','root')]:
            c=ObserverClient();c.auth_user=user;c.auth_role=role
            with self.subTest(user=user),self.assertRaises(StopDiagnostic):self.run_plan(c)
            self.assertTrue(c.closed);self.assertTrue(c.sessions[0].ended)
    def test_observer_target_rejects_other_profiles(self):
        for change in ({'uri':LAB_URI.replace('27019','27018')},{'database':'other'},
                       {'replica':'app_finanzas_dev_rs'},{'auth_user':'c3_apply'},
                       {'auth_role':'root'},{'environment_id':'invalid'},
                       {'metadata_uuid':'fake-uuid'}):
            with self.subTest(change=change),self.assertRaises(StopDiagnostic):replace(observer_target(),**change).validate()
    def test_live_physical_uuid_discrepancy_rejected(self):
        c=ObserverClient();c.pins['transactions']=Binary(b'z'*16,4)
        with self.assertRaises(StopDiagnostic):self.run_plan(c)
    def test_live_r6_discrepancy_rejected(self):
        c=ObserverClient();c.env='51f6339c-9659-46a4-bbac-2f358428f5fb'
        with self.assertRaises(StopDiagnostic):self.run_plan(c)
    def test_snapshot_drift_not_complete(self):
        c=ObserverClient([row(1)]);c.drift=True
        c,e=self.run_plan(c)
        self.assertFalse(e.plan.complete_at_T);self.assertEqual(e.plan.intents,())
        self.assertTrue(c.closed);self.assertEqual(len(c.sessions),1)
    def test_observer_plan_not_accepted_by_apply_adapter(self):
        c,e=self.run_plan()
        t=observer_target()
        auth=Authorization(RUN,e.plan.digest,t,e.plan.scope,'b'*40,'epoch',time.monotonic()+60,True)
        permit=SyntheticPermit(auth,LAB_NONCE,t.journal_uuid,True,True)
        with self.assertRaises(Conflict):SyntheticMongoApplyAdapter(c,e.plan,permit,Verifier(t))
        self.assertEqual(request_mongodb_execution(e)['error'],'external_exclusion_unproven')
    def test_candidate_binding_distinct_from_apply(self):
        self.assertNotEqual(observer_target().binding(),target().binding())
    def test_empty_collection_complete_read_plan(self):
        c,e=self.run_plan(ObserverClient());self.assertTrue(e.plan.complete_at_T)
        self.assertEqual(e.plan.intents,());self.assertEqual(len(c.sessions),1)
    def test_duplicate_ids_block_and_drop_intents(self):
        c,e=self.run_plan(ObserverClient([row(1),row(2,id='synthetic-1')]))
        self.assertEqual(e.plan.state,'blocked');self.assertEqual(e.plan.intents,())
    def test_cleanup_failure_never_returns_complete_evidence(self):
        c=ObserverClient();c.cleanup_failure=True
        with self.assertRaises(StopDiagnostic):self.run_plan(c)
    def test_connection_error_sanitized(self):
        c=ObserverClient()
        with patch.object(c,'command',side_effect=RuntimeError('SECRET_CONNECTION')):
            with self.assertRaises(StopDiagnostic) as error:self.run_plan(c)
        self.assertNotIn('SECRET_CONNECTION',str(error.exception))
        self.assertTrue(c.closed)
    def test_limits_rejected_before_any_command(self):
        from backend.history_diagnostics import Limits
        c=ObserverClient()
        with self.assertRaises(StopDiagnostic):self.run_plan(c,limits=Limits(batch_documents=101))
        self.assertEqual(c.calls,[]);self.assertEqual(c.sessions,[])
    def test_apply_target_validation_not_relaxed(self):
        with self.assertRaises(StopDiagnostic):replace(target(),approved=False,physical_pins_approved=False).validate()
    def test_history_budget_invalidates_plan(self):
        from backend.history_diagnostics import Limits
        c,e=self.run_plan(limits=Limits(history_documents=1))
        self.assertFalse(e.plan.complete_at_T);self.assertEqual(e.plan.intents,())
    def test_snapshot_or_cursor_loss_never_completes(self):
        from pymongo.errors import OperationFailure,ConnectionFailure
        for error in (OperationFailure('SECRET',code=286),OperationFailure('SECRET',code=43),ConnectionFailure('SECRET')):
            c=ObserverClient([row(1)]);c.cursor_failure=error
            c,e=self.run_plan(c)
            self.assertFalse(e.plan.complete_at_T);self.assertEqual(e.plan.intents,())
            self.assertNotIn('SECRET',json.dumps(e.public_report()))
            self.assertEqual(len(c.sessions),1);self.assertTrue(c.sessions[0].ended)
    def test_observer_report_has_no_individual_sources(self):
        c,e=self.run_plan(ObserverClient([row(1,name='PRIVATE_SECRET')]))
        report=json.dumps(e.public_report())
        for private in ('PRIVATE_SECRET','synthetic-1','2026-W40','source_sha256','physical_id'):
            self.assertNotIn(private,report)


if __name__ == '__main__':unittest.main()
