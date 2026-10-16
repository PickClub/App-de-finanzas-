"""Offline synthetic runner and explicit MongoDB execution blocker.

No MongoClient, live preparation or writable connection path exists. The local
infrastructure does not yet supply defensible external writer exclusion.
"""
from dataclasses import dataclass, field, replace, asdict
from datetime import datetime, timezone
import hashlib
import io
import json
import sys
import time
from uuid import uuid4, UUID

from bson import BSON
from bson.binary import Binary

from backend.history_apply import Authorization, Observation, RunState, Budgets, apply_plan, reconcile
from backend.history_apply_mongodb import SyntheticMongoApplyAdapter, SyntheticPermit, JOURNAL, MARKER
from backend.history_diagnostics import Target, LOCAL_URI
from backend.history_provisioning import build_plan
from backend.history_apply_lab import LabTarget, LabCredentials, lab_client_options


class RunnerBlocked(Exception):
    pass


@dataclass(frozen=True)
class Preparation:
    mode: str
    nonce: str
    database: str
    environment_id: str
    collection_uuid: Binary
    journal_uuid: Binary

    def validate(self):
        if (self.mode != 'synthetic_only' or type(self.nonce) is not str
                or len(self.nonce) != 32 or any(c not in '0123456789abcdef' for c in self.nonce)
                or self.database != 'test_c3_apply_' + self.nonce):
            raise RunnerBlocked()
        try:
            env = UUID(self.environment_id)
            if env.version != 4 or str(env) != self.environment_id: raise ValueError()
            for value in (self.collection_uuid, self.journal_uuid):
                if type(value) is not Binary or value.subtype != 4 or len(value) != 16: raise ValueError()
        except Exception: raise RunnerBlocked() from None

    def digest(self):
        self.validate()
        return hashlib.sha256(BSON.encode(asdict(self))).hexdigest()


def new_preparation():
    """Generate pins, never read a server or approve the generated values."""
    nonce = uuid4().hex
    return Preparation('synthetic_only', nonce, 'test_c3_apply_' + nonce, str(uuid4()),
                       Binary(uuid4().bytes, 4), Binary(uuid4().bytes, 4))


@dataclass(frozen=True)
class FixtureApproval:
    """Independent approval fixture. Never valid as operational authorization."""
    preparation_digest: str
    plan_digest: str
    run_id: str
    mode: str = 'offline_fixture_only'
    approved: bool = False


@dataclass
class OfflineCatalog:
    """Simulated catalog, not proof that a live database is absent."""
    existing_names: set = field(default_factory=set)
    prepared: Preparation | None = None
    rows: list = field(default_factory=list, repr=False)
    writers: set = field(default_factory=lambda: {'fixture-runner'})
    ddl_expected: bool = True
    unknown_inflight: bool = False

    def prepare(self, request, rows):
        if type(request) is not Preparation: raise RunnerBlocked()
        request.validate()
        if self.prepared is not None or request.database in self.existing_names: raise RunnerBlocked()
        self.existing_names.add(request.database)
        self.prepared = request
        # Roundtrip copies prevent modifying financial fixtures owned by a caller.
        self.rows = [BSON.encode(r) for r in rows]


class ExternalExclusionVerifier:
    """Fail closed: no provider is implemented or autoapproved for real use."""
    def verify(self, *_args):
        raise RunnerBlocked('external_exclusion_unproven')


def lab_connection_spec(target, credentials):
    """Offline validation only. No client, credential file read or approval here."""
    try:
        return lab_client_options(target, credentials)
    except Exception:
        raise RunnerBlocked('invalid_lab_profile') from None


def request_mongodb_execution(*_args, **_kwargs):
    """No credential/client factory is called, even with alleged approval or pins."""
    return {'state': 'blocked', 'error': 'external_exclusion_unproven',
            'connection_attempted': False, 'operational_apply_authorized': False,
            'indexed_reads_allowed': False, 'financial_correctness_asserted': False}


class _FixtureVerifier:
    """Only proves simulated state of the exact OfflineCatalog under test."""
    def __init__(self, catalog, target):
        if type(catalog) is not OfflineCatalog: raise RunnerBlocked()
        self.catalog, self.target = catalog, target
    def verify(self, permit, deadline):
        p = self.catalog.prepared
        if (p is None or self.catalog.writers != {'fixture-runner'} or not self.catalog.ddl_expected
                or self.catalog.unknown_inflight or p.nonce != permit.nonce
                or p.collection_uuid != permit.authorization.target.collection_uuid
                or p.journal_uuid != permit.journal_uuid
                or p.environment_id != permit.authorization.target.environment_id
                or self.target != permit.authorization.target):
            raise RunnerBlocked()
        # Duplicates are checked over the complete bounded fake scope, not a batch.
        seen = set()
        duplicates = 0
        for raw in self.catalog.rows:
            document = BSON(raw).decode()
            logical = (document.get('user_id'), document.get('id'))
            if logical in seen: duplicates += 1
            seen.add(logical)
        return Observation(self.target, 'offline-fixture-window', True, True, True, True, duplicates)


def fixture_context(catalog, *, run_id=None):
    """Offline PLAN and fake client creation only. No live reader is instantiated."""
    if type(catalog) is not OfflineCatalog or catalog.prepared is None: raise RunnerBlocked()
    p = catalog.prepared
    p.validate()
    from backend.tests.test_history_diagnostics import Reader, T
    from backend.tests.test_history_apply_mongodb_adapter import Client
    target = Target(LOCAL_URI, p.database, 'transactions', p.collection_uuid,
                    p.environment_id, 'default-user', 1, 1, True)
    rows = [BSON(raw).decode() for raw in catalog.rows]
    run_id = str(uuid4()) if run_id is None else run_id
    plan = build_plan(Reader(rows), target, run_id, T)
    # Existing driver fake supports dynamic namespace here; no real client accepted.
    class OfflineClient(Client):
        def __getitem__(self, name):
            if name == p.database: return self
            if name in self.docs:
                from backend.tests.test_history_apply_mongodb_adapter import Collection
                return Collection(self, name)
            raise RunnerBlocked()
    client = OfflineClient(rows, target)
    client.docs['moneyflow_metadata'] = [
        {'_id': 'financial-context', 'version': 1, 'environment_id': p.environment_id,
         'created_at': datetime.now(timezone.utc).isoformat()},
        {'_id': MARKER, 'mode': 'synthetic_only', 'nonce': p.nonce,
         'collection_uuid': p.collection_uuid, 'journal_uuid': p.journal_uuid,
         'environment_id': p.environment_id}]
    client.uuids = {'transactions': p.collection_uuid, JOURNAL: p.journal_uuid}
    return target, plan, client


def run_fixture(catalog, target, plan, client, approval, *, fault=None, budgets=None):
    """Explicit offline scenario. A real MongoClient is rejected before any call."""
    from backend.tests.test_history_apply_mongodb_adapter import Client
    if (type(catalog) is not OfflineCatalog or catalog.prepared is None
            or not isinstance(client, Client) or type(client).__module__ != __name__
            or type(approval) is not FixtureApproval or approval.mode != 'offline_fixture_only'
            or approval.approved is not True or approval.preparation_digest != catalog.prepared.digest()
            or approval.plan_digest != plan.digest or approval.run_id != plan.run_id):
        raise RunnerBlocked()
    p = catalog.prepared
    expected_target = Target(LOCAL_URI, p.database, 'transactions', p.collection_uuid,
                             p.environment_id, 'default-user', 1, 1, True)
    if target != expected_target or plan.destination_id != target.binding(): raise RunnerBlocked()
    authorization = Authorization(plan.run_id, plan.digest, target, plan.scope,
                                  'f'*40, 'offline-fixture-window', time.monotonic()+60, True)
    permit = SyntheticPermit(authorization, p.nonce, p.journal_uuid, True, True)
    adapter = SyntheticMongoApplyAdapter(client, plan, permit, _FixtureVerifier(catalog, target))
    state = RunState()
    before = {d['_id']: BSON.encode(d) for d in client.docs['transactions']}
    financial_before = {d['_id']: BSON.encode({k:v for k,v in d.items() if k != '_history_keys'})
                        for d in client.docs['transactions']}
    from pymongo.errors import OperationFailure
    if fault == 'cas': client.cas_zero = True
    elif fault == 'receipt': client.insert_error = OperationFailure('injected')
    elif fault == 'transient': client.commit_errors = [OperationFailure('injected', details={'errorLabels':['TransientTransactionError']})]
    elif fault == 'lost_confirm': client.commit_errors = ['after']
    elif fault == 'context': client.docs['moneyflow_metadata'][0]['environment_id'] = str(uuid4())
    elif fault not in (None, 'null'): raise RunnerBlocked()
    if fault == 'null': client.docs['transactions'][0]['_history_keys'] = None
    report = apply_plan(adapter, plan, target, authorization, state,
                        budgets=budgets if budgets is not None else (Budgets(commit_attempts=1) if fault == 'lost_confirm' else Budgets()))
    if report['state'] == 'uncertain':
        reader = SyntheticMongoApplyAdapter(client, plan, replace(permit, operation='reconcile'),
                                            _FixtureVerifier(catalog, target))
        result = reconcile(reader, plan, target, authorization, state)
        report['reconciliation_state'] = result['state']
    for op, name, content, session in client.calls:
        if op not in ('hello','buildInfo','listCollections','find','insert','update'): raise RunnerBlocked()
        if op == 'insert' and name != JOURNAL: raise RunnerBlocked()
        if op == 'update' and (name != 'transactions' or content[2] is not False
                             or set(content[1]) != {'$set'} or set(content[1]['$set']) != {'_history_keys'}):
            raise RunnerBlocked()
    if not client.closed or any(not s.ended for s in client.sessions): raise RunnerBlocked()
    if financial_before != {d['_id']: BSON.encode({k:v for k,v in d.items() if k != '_history_keys'})
                            for d in client.docs['transactions']}: raise RunnerBlocked()
    # Do not return documents, IDs, pins, fingerprints or audit command bodies.
    report.update(offline_only=True, controlled_fault_injection=fault is not None,
                  real_writer_exclusion_demonstrated=False, command_policy_checked=True, financial_bson_unchanged=True,
                  resources_closed=True, metadata_changed_documents=sum(
                      before[d['_id']] != BSON.encode(d) for d in client.docs['transactions']))
    return report


def main(argv=None, output=None):
    argv = sys.argv[1:] if argv is None else argv
    output = sys.stdout if output is None else output
    if argv == ['--offline-tests']:
        import unittest
        result = unittest.TextTestRunner(stream=output).run(unittest.defaultTestLoader.loadTestsFromTestCase(RunnerTests))
        return 0 if result.wasSuccessful() else 4
    print(json.dumps(request_mongodb_execution(), sort_keys=True), file=output)
    return 4


# Tests live in this authorized file; no additional test path is required.
import unittest


class RunnerTests(unittest.TestCase):
    def case(self):
        from backend.tests.test_history_diagnostics import row
        p = new_preparation(); catalog = OfflineCatalog(); catalog.prepare(p,[row(1)])
        target, plan, client = fixture_context(catalog)
        approval = FixtureApproval(p.digest(), plan.digest, plan.run_id, approved=True)
        return catalog, target, plan, client, approval
    def test_import_no_connection(self):
        import subprocess
        script="""
from unittest.mock import patch
with patch('pymongo.MongoClient',side_effect=AssertionError('network')),patch('builtins.open',side_effect=AssertionError('files')):
 import backend.tests.history_apply_synthetic_runner
"""
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_new_identity_and_existing_base_rejected(self):
        p=new_preparation();p.validate()
        with self.assertRaises(RunnerBlocked):OfflineCatalog({p.database}).prepare(p,[])
        self.assertNotEqual(p.database,new_preparation().database)
    def test_reject_generic_real_destination(self):
        p=new_preparation()
        with self.assertRaises(RunnerBlocked):replace(p,database='moneyflow').validate()
        with self.assertRaises(RunnerBlocked):replace(p,mode='real').validate()
    def test_independent_approval_required(self):
        c,t,p,client,a=self.case()
        with self.assertRaises(RunnerBlocked):run_fixture(c,t,p,client,replace(a,approved=False))
        self.assertFalse(client.calls)
        with self.assertRaises(RunnerBlocked):run_fixture(c,t,p,client,replace(a,preparation_digest='other'))
    def test_pins_and_target_changes_rejected(self):
        c,t,p,client,a=self.case()
        for changed in (replace(t,environment_id=str(uuid4())),replace(t,collection_uuid=Binary(b'x'*16,4)),
                        replace(t,uri='mongodb://remote/')):
            with self.assertRaises(RunnerBlocked):run_fixture(c,changed,p,client,a)
        self.assertFalse(client.calls)
    def test_missing_ready(self):
        report=run_fixture(*self.case())
        self.assertEqual(report['state'],'confirmed');self.assertTrue(report['financial_bson_unchanged'])
    def test_null_cas_and_atomicity_failure(self):
        for fault in ('null','cas','receipt'):
            report=run_fixture(*self.case(),fault=fault)
            self.assertEqual(report['state'],'blocked');self.assertEqual(report['confirmed_documents'],0)
    def test_transient_and_uncertain_original_confirmation(self):
        self.assertEqual(run_fixture(*self.case(),fault='transient')['state'],'confirmed')
        report=run_fixture(*self.case(),fault='lost_confirm')
        self.assertEqual(report['state'],'uncertain');self.assertEqual(report['reconciliation_state'],'original_confirmed')
    def test_context_failure(self):
        self.assertEqual(run_fixture(*self.case(),fault='context')['state'],'blocked')
    def test_unknown_writers_ddl_or_inflight_rejected(self):
        for attr,value in (('writers',{'fixture-runner','external'}),('ddl_expected',False),('unknown_inflight',True)):
            c,t,p,client,a=self.case();setattr(c,attr,value)
            report=run_fixture(c,t,p,client,a)
            self.assertEqual(report['state'],'blocked');self.assertFalse([x for x in client.calls if x[0] in ('insert','update')])
    def test_exclusion_operational_gate_has_no_bypass(self):
        with self.assertRaises(RunnerBlocked):ExternalExclusionVerifier().verify(True)
        called=[]
        report=request_mongodb_execution(approved=True,verifier=lambda:True,client_factory=lambda:called.append(1))
        self.assertFalse(report['connection_attempted']);self.assertFalse(called)
        self.assertEqual(report['error'],'external_exclusion_unproven')
    def test_owner_and_restart_blocks(self):
        c,t,p,client,a=self.case();client.docs[JOURNAL].append({'_id':'execution','owner':'other'})
        self.assertEqual(run_fixture(c,t,p,client,a)['state'],'blocked');self.assertFalse(client.sessions)
    def test_private_report(self):
        encoded=json.dumps(run_fixture(*self.case()))
        for token in ('mongodb://','synthetic-1','70.123','2026-W40','source_sha256','physical_id'):
            self.assertNotIn(token,encoded)
    def test_resource_budget_blocks_and_closes(self):
        report=run_fixture(*self.case(),budgets=replace(Budgets(),document_bytes=1))
        self.assertEqual(report['state'],'blocked');self.assertTrue(report['resources_closed'])
    def test_empty_fixture_plan(self):
        catalog=OfflineCatalog();p=new_preparation();catalog.prepare(p,[])
        t,plan,client=fixture_context(catalog)
        a=FixtureApproval(p.digest(),plan.digest,plan.run_id,approved=True)
        r=run_fixture(catalog,t,plan,client,a)
        self.assertEqual(r['confirmed_documents'],0);self.assertEqual(r['state'],'confirmed')
        self.assertFalse(r['coverage_complete_asserted'])
    def test_reject_real_client_before_operations(self):
        from unittest.mock import MagicMock
        c,t,p,client,a=self.case();real_like=MagicMock()
        with self.assertRaises(RunnerBlocked):run_fixture(c,t,p,real_like,a)
        self.assertFalse(real_like.mock_calls)
    def test_preparation_cannot_overwrite_or_reuse(self):
        catalog=OfflineCatalog();p=new_preparation();catalog.prepare(p,[])
        with self.assertRaises(RunnerBlocked):catalog.prepare(new_preparation(),[])
    def test_injection_never_claims_real_exclusion(self):
        report=run_fixture(*self.case(),fault='cas')
        self.assertTrue(report['controlled_fault_injection'])
        self.assertFalse(report['real_writer_exclusion_demonstrated'])

    def test_main_never_executes_mongodb(self):
        output=io.StringIO();self.assertEqual(main(['--execute-synthetic','--approve'],output),4)
        self.assertEqual(json.loads(output.getvalue())['state'],'blocked')


if __name__ == '__main__':
    raise SystemExit(main())
