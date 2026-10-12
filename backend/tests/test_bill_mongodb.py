"""Opt-in R2 integration tests. Only a newly generated loopback database.

MONEYFLOW_R2_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_bill_mongodb
The new synthetic database is retained; no existing database is queried or cleaned.
"""
import asyncio
import json
import os
import unittest
import uuid

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import monitoring
from pymongo.errors import OperationFailure
from backend.tests.test_bill_validation import bill_context, synthetic_bill


class Audit(monitoring.CommandListener):
    def __init__(self):
        self.events = []

    def started(self, event):
        self.events.append((event.database_name, event.command_name, event.connection_id))

    def succeeded(self, event):
        pass

    def failed(self, event):
        pass


class CollectionProxy:
    def __init__(self, collection, fail):
        self.collection, self.fail = collection, fail

    def __getattr__(self, name):
        return getattr(self.collection, name)

    async def insert_one(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError('Injected failure at isolated insert')
        return await self.collection.insert_one(*args, **kwargs)


class DBProxy:
    def __init__(self, database, client, name, fail=None):
        self.database, self.client, self.name, self.fail = database, client, name, fail

    def __getattr__(self, name):
        assert self.database.name == self.name and self.client.address == ('127.0.0.1', 27018)
        return CollectionProxy(self.database[name], name == self.fail)


class LostResponse(httpx.ASGITransport):
    async def handle_async_request(self, request):
        response = await super().handle_async_request(request)
        if response.status_code == 200 and request.method == 'POST':
            raise httpx.ReadError('Response lost after the real transaction committed')
        return response


@unittest.skipUnless(os.environ.get('MONEYFLOW_R2_REAL_TESTS') == '1', 'Real R2 tests require explicit opt-in')
class BillMongoDBTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.name = 'test_r2_validation_' + uuid.uuid4().hex
        self.audit = Audit()
        self.client = AsyncIOMotorClient(
            'mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true',
            serverSelectionTimeoutMS=5000, event_listeners=[self.audit])
        self.db = self.client[self.name]
        hello = await self.client.admin.command('hello')
        self.assertEqual(self.client.address, ('127.0.0.1', 27018))
        self.assertEqual(hello['setName'], 'app_finanzas_dev_rs')
        self.assertTrue(hello['isWritablePrimary'])
        self.assertIsNotNone(hello.get('logicalSessionTimeoutMinutes'))
        self.assertEqual(self.db.name, self.name)
        self.assertTrue(self.name.startswith('test_r2_validation_'))
        self.assertEqual(await self.db.list_collection_names(), [])
        for collection in ('bills', 'bill_payments', 'accounts', 'transactions', 'categories',
                           'recurring_payments', 'recurring_payment_records'):
            await self.db.create_collection(collection)
        self.results = []
        print('R2 NEW DB VERIFIED:', self.name, flush=True)

    async def asyncTearDown(self):
        try:
            for database, command, address in self.audit.events:
                self.assertIn(database, (self.name, 'admin'))
                self.assertEqual(address, ('127.0.0.1', 27018))
                self.assertNotIn(command, ('delete', 'dropDatabase', 'drop'))
            print('R2 SYNTHETIC DB RETAINED:', self.name, 'scenarios:', len(self.results), flush=True)
        finally:
            self.client.close()

    async def fixture(self, label, monthly=False, linked=False):
        bid = label + '-' + uuid.uuid4().hex
        accounts = [bid + '-a', bid + '-b']
        await self.db.accounts.insert_many([dict(_id=a, id=a, user_id='default-user', name='Synthetic',
                                                initial_balance=1000, current_balance=1000) for a in accounts])
        bill = synthetic_bill(bid, 'monthly' if monthly else 'once')
        if linked:
            bill['recurring_payment_id'] = bid + '-recurring'
            await self.db.recurring_payments.insert_one(dict(
                _id=bill['recurring_payment_id'], id=bill['recurring_payment_id'], user_id='default-user',
                name='Synthetic recurring', pauses=[], end_date=None,
                versions=[dict(valid_from='2026-10-01', start_date='2026-10-20',
                               frequency='monthly', due_day=20, amount=100)]))
        await self.db.bills.insert_one(bill)
        ns, app = bill_context(DBProxy(self.db, self.client, self.name), self.client)

        async def request(method, path, payload=None, key=None, lost=False):
            transport = (LostResponse if lost else httpx.ASGITransport)(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url='http://synthetic-r2.invalid') as c:
                return await c.request(method, '/api' + path, **({'json': payload} if payload is not None else {}),
                                       headers={'Idempotency-Key': key} if key else {})

        async def pay(amount=70, account=0, key='one', lost=False):
            return await request('POST', f'/bills/{bid}/payments', dict(amount=amount,
                account_id=accounts[account], date='2026-10-12T12:00:00+00:00', notes='Synthetic'), key, lost)

        async def snapshot():
            payments = await self.db.bill_payments.find({'bill_id': bid}).to_list(100)
            movements = await self.db.transactions.find({'bill_id': bid}).to_list(100)
            records = await self.db.recurring_payment_records.find({'recurring_id': bill.get('recurring_payment_id')}).to_list(100) if linked else []
            current = await self.db.bills.find_one({'id': bid})
            balances = [(await self.db.accounts.find_one({'id': a}))['current_balance'] for a in accounts]
            for payment in payments:
                movement = next(m for m in movements if m['id'] == payment['transaction_id'])
                self.assertEqual(movement['bill_payment_id'], payment['id'])
                self.assertEqual(movement['amount'], payment['amount'])
            self.assertEqual(len(movements), len(payments))
            for index, account in enumerate(accounts):
                self.assertEqual(balances[index], 1000 - sum(m['amount'] for m in movements if m['account_id'] == account))
            for record in records:
                self.assertIn(record['transaction_id'], [m['id'] for m in movements])
            paid = sum(p['amount'] for p in payments)
            self.assertLessEqual(paid, current['amount'])
            return dict(paid=paid, payments=len(payments), movements=len(movements), balances=balances,
                        amount=current['amount'], revision=current.get('_payment_revision', 0),
                        next=current.get('next_bill_id'), recurring_records=len(records))

        return bid, accounts, bill, ns, request, pay, snapshot

    def rendezvous_before_lock(self, ns):
        original = ns['_bill_for_write']
        arrived = 0
        gate = asyncio.Event()

        async def concurrent(*args, **kwargs):
            nonlocal arrived
            arrived += 1
            if arrived <= 2:
                if arrived == 2:
                    gate.set()
                await asyncio.wait_for(gate.wait(), 15)
            return await original(*args, **kwargs)
        ns['_bill_for_write'] = concurrent

    def record(self, label, state):
        self.results.append(dict(case=label, **state))
        print('PASS R2:', label, json.dumps(state), flush=True)

    async def test_concurrency_idempotency_and_atomicity(self):
        matrix = [
            ('overpay-different-accounts', (70, 70), False, False, False, False, (200, 422), 70),
            ('overpay-same-account', (70, 70), True, False, False, False, (200, 422), 70),
            ('exact-monthly-different-accounts', (50, 50), False, False, True, False, (200, 200), 100),
            ('exact-same-account', (70, 30), True, False, False, False, (200, 200), 100),
            ('partial-different-accounts', (30, 40), False, False, False, False, (200, 200), 70),
            ('partial-same-account', (30, 40), True, False, False, False, (200, 200), 70),
            ('same-key-identical', (70, 70), True, True, False, False, (200, 200), 70),
            ('same-key-different-payload', (70, 70), False, True, False, False, (200, 409), 70),
            ('linked-recurring-exact', (30, 70), False, False, True, True, (200, 200), 100),
            ('linked-recurring-overpay', (70, 70), False, False, True, True, (200, 422), 70),
        ]
        for label, amounts, same_account, same_key, monthly, linked, statuses, total in matrix:
            with self.subTest(case=label):
                bid, accounts, bill, ns, req, pay, snap = await self.fixture(label, monthly, linked)
                self.rendezvous_before_lock(ns)
                responses = await asyncio.gather(pay(amounts[0], 0, 'one'), pay(amounts[1], 0 if same_account else 1, 'one' if same_key else 'two'))
                self.assertEqual(sorted(r.status_code for r in responses), sorted(statuses), [r.text for r in responses])
                state = await snap()
                self.assertEqual(state['paid'], total)
                self.assertEqual(state['revision'], state['payments'])
                if monthly and total == 100:
                    self.assertIsNotNone(state['next'])
                    self.assertEqual(await self.db.bills.count_documents({'series_id': bid}), 2)
                if linked:
                    self.assertEqual(state['recurring_records'], state['payments'])
                self.record(label, state)

        for amount in (50, 200):
            label = 'concurrent-amount-edit-' + str(amount)
            with self.subTest(case=label):
                bid, accounts, bill, ns, req, pay, snap = await self.fixture(label)
                self.rendezvous_before_lock(ns)
                answers = await asyncio.gather(pay(), req('PUT', f'/bills/{bid}', dict(name='Synthetic', amount=amount, due_date='2026-10-20')))
                self.assertEqual(sorted(r.status_code for r in answers), [200, 422] if amount == 50 else [200, 200])
                state = await snap()
                if amount == 50:
                    self.assertIn((state['amount'], state['paid']), [(100, 70), (50, 0)])
                self.record(label, state)

        # Force the other valid serialization: the edit takes the write lock
        # before the payment tries it. This tests revalidation after a conflict,
        # rather than depending on whichever coroutine happened to win.
        bid, accounts, bill, ns, req, pay, snap = await self.fixture('edit-wins')
        original = ns['_bill_for_write']
        held, attempted = asyncio.Event(), asyncio.Event()
        async def edit_first(*args, **kwargs):
            if asyncio.current_task().get_name() == 'r2-edit-wins':
                result = await original(*args, **kwargs)
                held.set()
                await asyncio.wait_for(attempted.wait(), 15)
                return result
            await asyncio.wait_for(held.wait(), 15)
            attempted.set()
            return await original(*args, **kwargs)
        ns['_bill_for_write'] = edit_first
        edit = asyncio.create_task(req('PUT', f'/bills/{bid}', dict(name='Synthetic', amount=50, due_date='2026-10-20')), name='r2-edit-wins')
        payment = asyncio.create_task(pay(), name='r2-payment-after-edit')
        answers = await asyncio.gather(edit, payment)
        self.assertEqual([r.status_code for r in answers], [200, 422])
        state = await snap()
        self.assertEqual((state['amount'], state['paid']), (50, 0))
        self.record('amount-edit-wins-payment-revalidates', state)

        for label, fail, linked in [('rollback-movement', 'transactions', True), ('rollback-next-period', 'bills', False)]:
            with self.subTest(case=label):
                bid, accounts, bill, ns, req, pay, snap = await self.fixture(label, True, linked)
                ns['db'] = DBProxy(self.db, self.client, self.name, fail)
                self.assertEqual((await pay(100)).status_code, 500)
                state = await snap()
                self.assertEqual(state['paid'], 0)
                self.assertEqual(state['balances'], [1000, 1000])
                self.assertEqual(state['revision'], 0)
                self.assertEqual(state['recurring_records'], 0)
                self.assertEqual(await self.db.bills.find_one({'id': bid}), bill)
                self.record(label, state)

        bid, accounts, bill, ns, req, pay, snap = await self.fixture('lost-response')
        with self.assertRaises(httpx.ReadError):
            await pay(lost=True)
        self.assertEqual((await pay()).status_code, 200)
        state = await snap()
        self.assertEqual(state['payments'], 1)
        self.assertEqual(state['revision'], 1)
        self.record('lost-response-original-key', state)

        bid, accounts, bill, ns, req, pay, snap = await self.fixture('uncertain-commit')
        real_client = self.client
        class CommittedSession:
            def __init__(self, session):
                self.session = session
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                await self.session.end_session()
            async def with_transaction(self, callback, **options):
                await self.session.with_transaction(callback, **options)
                raise OperationFailure('Injected unavailable commit result AFTER commit', details={'errorLabels': ['UnknownTransactionCommitResult']})
        class UncertainClient:
            async def start_session(self):
                return CommittedSession(await real_client.start_session())
        ns['client'] = UncertainClient()
        self.assertEqual((await pay()).status_code, 503)
        state = await snap()
        self.assertEqual(state['payments'], 1)
        self.assertEqual(state['revision'], 1)
        ns['client'] = real_client
        self.assertEqual((await pay()).status_code, 200)
        self.assertEqual(await snap(), state)
        self.record('uncertain-commit-same-key-recovery', state)

        bid, accounts, bill, ns, req, pay, snap = await self.fixture('transient-conflict')
        original, attempts = ns['_bill_for_write'], 0
        async def transient(*args, **kwargs):
            nonlocal attempts
            result = await original(*args, **kwargs)
            attempts += 1
            if attempts == 1:
                raise OperationFailure('Injected aborted transient transaction', code=112, details={'errorLabels': ['TransientTransactionError']})
            return result
        ns['_bill_for_write'] = transient
        self.assertEqual((await pay()).status_code, 200)
        self.assertEqual(attempts, 2)
        state = await snap()
        self.assertEqual(state['revision'], 1)
        self.record('transient-conflict-revalidation', state)

        bid, accounts, bill, ns, req, pay, snap = await self.fixture('private-api')
        self.assertEqual((await pay()).status_code, 200)
        responses = [await req('GET', f'/bills/{bid}'), await req('GET', '/bills'), await req('GET', '/bills/summary'),
                     await req('PUT', f'/bills/{bid}', dict(name='Synthetic', amount=100, due_date='2026-10-20'))]
        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn('_payment_revision', response.text)
        self.record('no-internal-fields-in-public-api', await snap())
        self.assertEqual(len(self.results), 19)


if __name__ == '__main__':
    unittest.main()
