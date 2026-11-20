"""Bootstrap simulation only: all database operations use in-memory doubles."""

import ast
from copy import deepcopy
from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from backend.production_config import ConfigurationError

def load_contract_data():
    """Evaluate the actual pure contract definitions without auth/driver imports.

    This suite does not test authentication or transport. Reading just these AST
    nodes keeps the simulation executable without installing unrelated packages.
    """
    root = Path(__file__).resolve().parents[1]
    namespace = {}
    selections = (
        ("auth_mongodb.py", {"ACCOUNT_DATA_COLLECTIONS"}),
        ("production_services.py", {"UNIQUE_INDEXES", "index_plan"}),
    )
    for filename, names in selections:
        tree = ast.parse((root / filename).read_text())
        nodes = [node for node in tree.body if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)
        ) or (isinstance(node, ast.FunctionDef) and node.name in names)]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)
    return namespace


contract = load_contract_data()
auth_contract = ModuleType('backend.auth_mongodb')
auth_contract.ACCOUNT_DATA_COLLECTIONS = contract['ACCOUNT_DATA_COLLECTIONS']
service_contract = ModuleType('backend.production_services')
service_contract.index_plan = contract['index_plan']
# Only import dependencies are substituted; the initializer under test is real.
with patch.dict(sys.modules, {
    'backend.auth_mongodb': auth_contract,
    'backend.production_services': service_contract,
}):
    from backend.production_initializer import COLLECTIONS, Initializer, InitializationBlocked
index_plan = contract['index_plan']


def environment():
    hosts = ','.join(f'fixture-{n}.mongodb.net:27017' for n in range(3))
    return {
        'APP_ENV': 'production', 'PW_MONGO_TARGET': 'Pickwallet-prod',
        'PW_MONGO_NETWORK_MODE': 'atlas_allowlisted',
        'PW_MONGO_EGRESS_CIDRS': '8.8.8.8/32',
        'PW_MONGO_DATABASE': 'pickwallet_prod', 'PW_MONGO_HOSTS': hosts,
        'PW_MONGO_REPLICA_SET': 'fixture-rs',
        'PW_ENVIRONMENT_ID': '7ff73614-71ac-4e10-9a56-c9b4e78303b2',
        'PW_MONGO_URI': f'mongodb://fixture:fixture-password-only-123@{hosts}/pickwallet_prod?tls=true&replicaSet=fixture-rs&authSource=admin&authMechanism=SCRAM-SHA-256',
    }


class Collection:
    def __init__(self, database):
        self.database = database
        self.documents = []
        self.indexes = [{'key': {'_id': 1}, 'name': '_id_', 'v': 2}]

    def count_documents(self, query):
        return len(self.documents)

    def find_one(self, query):
        return next((deepcopy(row) for row in self.documents if row['_id'] == query['_id']), None)

    def list_indexes(self):
        return deepcopy(self.indexes)

    def create_index(self, keys, **options):
        self.database.write()
        self.indexes.append({'key': dict(keys), **options})

    def insert_one(self, document):
        self.database.write()
        if any(row['_id'] == document['_id'] for row in self.documents):
            raise RuntimeError('duplicate fixture identifier')
        self.documents.append(deepcopy(document))


class Database:
    name = 'pickwallet_prod'

    def __init__(self):
        env = environment()
        self.topology = {
            'setName': env['PW_MONGO_REPLICA_SET'],
            'hosts': env['PW_MONGO_HOSTS'].split(','), 'isWritablePrimary': True,
            'logicalSessionTimeoutMinutes': 30, 'maxWireVersion': 17,
        }
        self.client = SimpleNamespace(admin=SimpleNamespace(command=self.command))
        self.collections, self.options = {}, {}
        self.writes, self.fail_at = 0, None

    def command(self, name):
        assert name == 'hello'
        return deepcopy(self.topology)

    def write(self):
        self.writes += 1
        if self.fail_at == self.writes:
            raise RuntimeError('sensitive-fixture-error-must-not-escape')

    def __getitem__(self, name):
        # Read access does not create collections, matching PyMongo handles.
        return self.collections.get(name, Collection(self))

    def list_collections(self):
        return [{'name': name, 'type': 'collection', 'options': self.options.get(name, {})}
                for name in self.collections]

    def create_collection(self, name):
        self.write()
        if name in self.collections:
            raise RuntimeError('collection already exists')
        self.collections[name] = Collection(self)


class InitializerTests(unittest.TestCase):
    def setUp(self):
        # Fail closed if any test or imported helper attempts a real connection.
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            patcher = patch(target, side_effect=AssertionError('Network forbidden'))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.database = Database()
        self.initializer = Initializer(environment(), self.database)

    def initialize(self):
        plan = self.initializer.dry_run()
        self.initializer.apply(plan, authorized=True)

    def test_dry_run_is_read_only_and_complete(self):
        plan = self.initializer.dry_run()
        self.assertEqual(self.database.writes, 0)
        self.assertEqual(self.database.collections, {})
        self.assertEqual(len(COLLECTIONS), 24)
        self.assertEqual(len(index_plan()), 39)
        self.assertEqual(len(plan.actions), 24 + 39 + 1)

    def test_apply_requires_dry_run(self):
        with self.assertRaises(InitializationBlocked):
            self.initializer.apply(None, authorized=True)
        self.assertEqual(self.database.writes, 0)

    def test_apply_requires_separate_authorization(self):
        with self.assertRaises(InitializationBlocked):
            self.initializer.apply(self.initializer.dry_run())
        self.assertEqual(self.database.writes, 0)

    def test_full_initialization_and_no_duplicates(self):
        self.initialize()
        self.assertEqual(set(self.database.collections), set(COLLECTIONS))
        self.assertEqual(sum(len(c.documents) for c in self.database.collections.values()), 1)
        self.assertEqual(sum(len(c.indexes) - 1 for c in self.database.collections.values()), 39)
        writes = self.database.writes
        self.initialize()
        self.assertEqual(self.database.writes, writes)
        self.assertEqual(self.initializer.dry_run().actions, ())

    def test_old_plan_cannot_be_reused(self):
        plan = self.initializer.dry_run()
        self.initializer.apply(plan, authorized=True)
        with self.assertRaises(InitializationBlocked):
            self.initializer.apply(plan, authorized=True)

    def test_plan_from_another_operator_rejected(self):
        other = Initializer(environment(), self.database)
        with self.assertRaises(InitializationBlocked):
            other.apply(self.initializer.dry_run(), authorized=True)
        self.assertEqual(self.database.writes, 0)

    def test_wrong_database_handle(self):
        self.database.name = 'r3_security_synthetic'
        with self.assertRaises(InitializationBlocked):
            self.initializer.dry_run()
        self.assertEqual(self.database.writes, 0)

    def test_configuration_rejects_wrong_target_and_missing_marker(self):
        for key, value in [('PW_MONGO_TARGET', 'Other'), ('PW_MONGO_TARGET', ''),
                           ('APP_ENV', 'development'), ('PW_MONGO_DATABASE', 'test')]:
            env = {**environment(), key: value}
            with self.assertRaises((ConfigurationError, InitializationBlocked)):
                Initializer(env, self.database)

    def test_topology_mismatch(self):
        for key, value in [('setName', 'other'), ('hosts', ['localhost:27018']),
                           ('isWritablePrimary', False), ('maxWireVersion', 0),
                           ('logicalSessionTimeoutMinutes', None)]:
            original = deepcopy(self.database.topology)
            self.database.topology[key] = value
            with self.assertRaises(InitializationBlocked):
                self.initializer.dry_run()
            self.database.topology = original
        self.assertEqual(self.database.writes, 0)

    def test_unknown_collection_rejected(self):
        self.database.create_collection('unrelated')
        writes = self.database.writes
        with self.assertRaises(InitializationBlocked):
            self.initializer.dry_run()
        self.assertEqual(self.database.writes, writes)

    def test_any_existing_application_data_rejected(self):
        for name in COLLECTIONS:
            if name == 'moneyflow_metadata':
                continue
            db = Database()
            db.create_collection(name)
            db[name].documents.append({'_id': 'existing-owner-record'})
            with self.assertRaises(InitializationBlocked):
                Initializer(environment(), db).dry_run()
            self.assertEqual(len(db[name].documents), 1)
            self.assertEqual(db.writes, 1)

    def test_metadata_identity_and_unexpected_documents(self):
        self.initialize()
        metadata = self.database['moneyflow_metadata']
        original = deepcopy(metadata.documents)
        for key, value in [('environment_id', 'other'), ('version', 2), ('extra', 'unknown')]:
            metadata.documents = deepcopy(original)
            metadata.documents[0][key] = value
            with self.assertRaises(InitializationBlocked):
                self.initializer.dry_run()
        metadata.documents = original + [{'_id': 'extra'}]
        with self.assertRaises(InitializationBlocked):
            self.initializer.dry_run()

    def test_collection_options_rejected(self):
        self.database.create_collection('accounts')
        self.database.options['accounts'] = {'capped': True}
        with self.assertRaises(InitializationBlocked):
            self.initializer.dry_run()

    def test_incompatible_index_options_rejected(self):
        self.database.create_collection('auth_users')
        for options in ({}, {'unique': True, 'sparse': True},
                        {'unique': True, 'partialFilterExpression': {'email': {'$exists': True}}},
                        {'unique': True, 'collation': {'locale': 'en'}}):
            self.database['auth_users'].indexes = [{'key': {'email': 1}, **options}]
            with self.assertRaises(InitializationBlocked):
                self.initializer.dry_run()

    def test_state_change_after_dry_run_prevents_writes(self):
        plan = self.initializer.dry_run()
        self.database.create_collection('accounts')
        writes = self.database.writes
        with self.assertRaises(InitializationBlocked):
            self.initializer.apply(plan, authorized=True)
        self.assertEqual(self.database.writes, writes)

    def test_partial_failure_requires_fresh_plan_and_is_resumable(self):
        for failure in (1, 10, 25, 45, 64):
            db = Database()
            operator = Initializer(environment(), db)
            plan = operator.dry_run()
            db.fail_at = failure
            with self.assertRaisesRegex(InitializationBlocked, '^Initialization incomplete; inspect before retrying$'):
                operator.apply(plan, authorized=True)
            with self.assertRaises(InitializationBlocked):
                operator.apply(plan, authorized=True)
            db.fail_at = None
            operator.apply(operator.dry_run(), authorized=True)
            self.assertEqual(operator.dry_run().actions, ())
            self.assertEqual(sum(len(c.indexes) - 1 for c in db.collections.values()), 39)

    def test_read_error_sanitized_and_plan_invalidated(self):
        self.initializer.dry_run()
        with patch.object(self.database, 'list_collections', side_effect=RuntimeError('secret-fixture')):
            with self.assertRaisesRegex(InitializationBlocked, '^Inspection failed; no initialization authorized$'):
                self.initializer.dry_run()
        self.assertIsNone(self.initializer._approved_plan)

    def test_ttl_and_unique_index_contract_preserved(self):
        self.initialize()
        indexes = self.database['auth_rate_limits'].indexes
        self.assertIn({'key': {'expires': 1}, 'expireAfterSeconds': 0}, indexes)
        self.assertIn({'key': {'email': 1}, 'unique': True}, self.database['auth_users'].indexes)
        self.assertIn({'key': {'family_id': 1}}, self.database['auth_refresh'].indexes)

    def test_preexisting_metadata_requires_valid_aware_timestamp(self):
        self.database.create_collection('moneyflow_metadata')
        context = {
            '_id': 'financial-context', 'version': 1,
            'environment_id': environment()['PW_ENVIRONMENT_ID'],
        }
        invalid = (None, 123, '', 'not-a-date', '2026-02-30T12:00:00Z',
                   '2026-11-08', '2026-11-08T12:00:00', '2026-11-08T12:00:00+25:00')
        for value in invalid:
            with self.subTest(timestamp=value):
                self.database['moneyflow_metadata'].documents = [{**context, 'created_at': value}]
                with self.assertRaises(InitializationBlocked):
                    self.initializer.dry_run()
        self.database['moneyflow_metadata'].documents = [context]
        with self.assertRaises(InitializationBlocked):
            self.initializer.dry_run()
        self.assertEqual(self.database.writes, 1)

    def test_preexisting_metadata_accepts_aware_iso_formats(self):
        self.database.create_collection('moneyflow_metadata')
        for timestamp in ('2026-11-08T12:00:00Z', '2026-11-08T12:00:00+00:00',
                          '2026-11-08T06:00:00.123456-06:00'):
            with self.subTest(timestamp=timestamp):
                self.database['moneyflow_metadata'].documents = [{
                    '_id': 'financial-context', 'version': 1,
                    'environment_id': environment()['PW_ENVIRONMENT_ID'],
                    'created_at': timestamp,
                }]
                plan = self.initializer.dry_run()
                self.assertNotIn(('metadata', 'financial-context'), plan.actions)
        self.assertEqual(self.database.writes, 1)

    def test_metadata_timestamp_change_invalidates_prior_plan(self):
        self.database.create_collection('moneyflow_metadata')
        document = {
            '_id': 'financial-context', 'version': 1,
            'environment_id': environment()['PW_ENVIRONMENT_ID'],
            'created_at': '2026-11-08T12:00:00+00:00',
        }
        self.database['moneyflow_metadata'].documents = [document]
        plan = self.initializer.dry_run()
        document['created_at'] = '2026-11-08T12:01:00+00:00'
        with self.assertRaisesRegex(InitializationBlocked, '^Database changed after dry-run$'):
            self.initializer.apply(plan, authorized=True)
        self.assertEqual(self.database.writes, 1)


if __name__ == '__main__':
    unittest.main()
