"""Administrative connection tests: only injected in-memory clients; no database."""

from copy import deepcopy
from unittest.mock import MagicMock, patch
import unittest

from backend.production_admin_connector import connect_initializer, DATABASE_ACTIONS
from backend.production_config import ConfigurationError, MongoTarget
from backend.production_initializer import InitializationBlocked
from backend.tests.test_production_initializer import Database, environment


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network forbidden'))
            guard.start()
            self.addCleanup(guard.stop)
        self.env = environment()
        self.db = Database()
        self.client = MagicMock()
        self.client.__getitem__.side_effect = lambda name: self.db if name == 'pickwallet_prod' else None
        self.db.client = self.client
        self.grants = [
            {'resource': {'db': 'pickwallet_prod', 'collection': ''},
             'actions': sorted(DATABASE_ACTIONS)},
            {'resource': {'db': 'pickwallet_prod', 'collection': 'moneyflow_metadata'},
             'actions': ['insert']},
        ]
        self.client.admin.command.side_effect = self.command
        self.factory = MagicMock(return_value=self.client)
        self.dns_guard = patch.object(MongoTarget, 'verify_private_network')
        self.dns = self.dns_guard.start()
        self.addCleanup(self.dns_guard.stop)

    def command(self, name, **kwargs):
        if name == 'connectionStatus':
            self.assertEqual(kwargs, {'showPrivileges': True})
            return {'authInfo': {'authenticatedUserPrivileges': deepcopy(self.grants)}}
        return self.db.command(name)

    def open(self, env=None, **kwargs):
        return connect_initializer(env or self.env, connection_authorized=True,
                                   client_factory=self.factory, **kwargs)

    def test_default_denies_before_dns_or_driver(self):
        with self.assertRaisesRegex(InitializationBlocked, '^Explicit connection authorization required$'):
            with connect_initializer(self.env, client_factory=self.factory):
                self.fail('Denied context must never yield')
        self.dns.assert_not_called()
        self.factory.assert_not_called()

    def test_truthy_non_boolean_is_not_authorization(self):
        for authorization in ('yes', 1, object()):
            with self.subTest(authorization=type(authorization).__name__):
                with self.assertRaises(InitializationBlocked):
                    with connect_initializer(self.env, connection_authorized=authorization, client_factory=self.factory):
                        self.fail('Nonboolean authorization')
        self.dns.assert_not_called()
        self.factory.assert_not_called()

    def test_wrong_or_missing_target_fails_before_dns(self):
        for target in ('Other', ''):
            with self.assertRaises((ConfigurationError, InitializationBlocked)):
                with self.open({**self.env, 'PW_MONGO_TARGET': target}):
                    self.fail('Wrong target')
        self.dns.assert_not_called()
        self.factory.assert_not_called()

    def test_missing_secret_and_srv_fail_before_dns(self):
        for uri in ('', 'mongodb+srv://fixture:synthetic-password-only-123@fixture.mongodb.net/pickwallet_prod'):
            with self.assertRaises(ConfigurationError) as caught:
                with self.open({**self.env, 'PW_MONGO_URI': uri}):
                    self.fail('Invalid URI')
            self.assertNotIn('synthetic-password', str(caught.exception))
        self.dns.assert_not_called()
        self.factory.assert_not_called()

    def test_dns_rejection_prevents_client_construction(self):
        self.dns.side_effect = RuntimeError('synthetic-sensitive-value')
        with self.assertRaisesRegex(InitializationBlocked, '^Administrative inspection unavailable$'):
            with self.open():
                self.fail('DNS failure')
        self.factory.assert_not_called()

    def test_driver_failure_is_sanitized(self):
        self.factory.side_effect = RuntimeError('synthetic-sensitive-value')
        with self.assertRaisesRegex(InitializationBlocked, '^Administrative inspection unavailable$'):
            with self.open():
                self.fail('Driver failure')

    def test_success_uses_existing_tls_options_and_only_inspects(self):
        config = MongoTarget.load(self.env)
        with self.open() as (initializer, plan):
            self.factory.assert_called_once_with(config.mongo_uri, connect=False, **config.mongo_options())
            self.dns.assert_called_once()
            self.assertEqual(len(plan.actions), 64)
            self.assertEqual(self.db.writes, 0)
            self.assertEqual(self.db.collections, {})
            self.client.close.assert_not_called()
            self.assertEqual([call.args[0] for call in self.client.admin.command.call_args_list],
                             ['connectionStatus', 'hello'])
        self.client.close.assert_called_once()
        self.assertEqual(self.db.writes, 0)

    def test_plan_is_invalid_after_context_exit(self):
        with self.open() as (initializer, plan):
            pass
        with self.assertRaises(InitializationBlocked):
            initializer.apply(plan, authorized=True)
        self.assertEqual(self.db.writes, 0)

    def test_no_mutation_authorization_implied_by_connection(self):
        with self.open() as (initializer, plan):
            with self.assertRaises(InitializationBlocked):
                initializer.apply(plan)
        self.assertEqual(self.db.writes, 0)

    def test_caller_failure_closes_and_invalidates_plan_without_leaking(self):
        initializer = None
        with self.assertRaisesRegex(InitializationBlocked, '^Administrative inspection unavailable$'):
            with self.open() as (initializer, plan):
                raise ValueError('synthetic-sensitive-value')
        self.client.close.assert_called_once()
        self.assertIsNone(initializer._approved_plan)
        self.assertEqual(self.db.writes, 0)

    def test_privilege_failure_closes_before_inspection(self):
        self.grants[0]['actions'].append('dropDatabase')
        with self.assertRaises(InitializationBlocked):
            with self.open():
                self.fail('Excessive privilege')
        self.client.close.assert_called_once()
        self.assertEqual([call.args[0] for call in self.client.admin.command.call_args_list], ['connectionStatus'])
        self.assertEqual(self.db.writes, 0)

    def test_every_required_action_is_enforced(self):
        original = deepcopy(self.grants)
        for index, action in [(0, a) for a in DATABASE_ACTIONS] + [(1, 'insert')]:
            with self.subTest(action=action):
                self.grants = deepcopy(original)
                self.grants[index]['actions'].remove(action)
                with self.assertRaises(InitializationBlocked):
                    with self.open():
                        self.fail('Missing action')
        self.assertEqual(self.db.writes, 0)

    def test_application_runtime_role_is_not_bootstrap_role(self):
        self.grants = [{'resource': {'db': 'pickwallet_prod', 'collection': ''},
                        'actions': ['find', 'insert', 'update', 'remove', 'listIndexes']}]
        with self.assertRaises(InitializationBlocked):
            with self.open():
                self.fail('Runtime identity cannot bootstrap')
        self.assertEqual(self.db.writes, 0)

    def test_insert_cannot_be_database_wide(self):
        self.grants[0]['actions'].append('insert')
        self.grants.pop()
        with self.assertRaises(InitializationBlocked):
            with self.open():
                self.fail('Database-wide insert')

    def test_wrong_database_global_and_other_collection_privileges_rejected(self):
        for resource in ({'db': 'r3_security_synthetic', 'collection': ''}, {'cluster': True},
                         {'db': 'pickwallet_prod', 'collection': 'accounts'}):
            with self.subTest(resource=resource):
                self.grants[1]['resource'] = resource
                with self.assertRaises(InitializationBlocked):
                    with self.open():
                        self.fail('Wrong privilege scope')
        self.assertEqual(self.db.writes, 0)

    def test_wrong_replica_rejected_and_closed(self):
        self.db.topology['setName'] = 'other'
        with self.assertRaises(InitializationBlocked):
            with self.open():
                self.fail('Topology mismatch')
        self.client.close.assert_called_once()
        self.assertEqual(self.db.writes, 0)

    def test_client_cleanup_error_is_sanitized(self):
        self.client.close.side_effect = RuntimeError('synthetic-sensitive-value')
        with self.assertRaisesRegex(InitializationBlocked, '^Administrative client cleanup failed$'):
            with self.open():
                pass
        self.assertEqual(self.db.writes, 0)

    def test_existing_application_data_is_not_adopted(self):
        self.db.create_collection('accounts')
        self.db['accounts'].documents.append({'_id': 'fixture-existing'})
        writes = self.db.writes
        with self.assertRaises(InitializationBlocked):
            with self.open():
                self.fail('Existing data')
        self.client.close.assert_called_once()
        self.assertEqual(self.db.writes, writes)

    def test_default_driver_import_is_only_used_after_authorization(self):
        with patch('pymongo.MongoClient', return_value=self.client) as default_factory:
            with connect_initializer(self.env, connection_authorized=True):
                pass
            default_factory.assert_called_once()
        self.assertEqual(self.db.writes, 0)


if __name__ == '__main__':
    unittest.main()
