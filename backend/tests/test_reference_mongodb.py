"""Opt-in R3: new isolated database per case; never cleans existing databases.

MONEYFLOW_R3_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_reference_mongodb
"""
import asyncio
import os
import unittest
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from backend.tests.test_bill_mongodb import Audit
from backend.tests.test_reference_integrity import ReferenceCases, context


class ConflictAudit(Audit):
    def __init__(self):
        super().__init__()
        self.failures = []

    def failed(self, event):
        self.failures.append(event.failure.get('code'))


class DBProxy:
    def __init__(self, db, client, fail=None):
        self.database, self.client, self.fail = db, client, fail

    def __getattr__(self, name):
        assert self.database.name.startswith('test_r3_validation_')
        assert self.client.address == ('127.0.0.1', 27018)
        col = self.database[name]
        if self.fail and self.fail[0] == name:
            class Proxy:
                def __getattr__(inner, method):
                    if method == self.fail[1]:
                        async def failed(*args, **kwargs):
                            raise OperationFailure('R3 synthetic injected failure')
                        return failed
                    return getattr(col, method)
            return Proxy()
        return col


@unittest.skipUnless(os.environ.get('MONEYFLOW_R3_REAL_TESTS') == '1', 'Real R3 tests require explicit opt-in')
class ReferenceMongoDBTests(ReferenceCases, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.name = 'test_r3_validation_' + uuid.uuid4().hex
        self.audit = ConflictAudit()
        self.client = AsyncIOMotorClient(
            'mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true',
            serverSelectionTimeoutMS=5000, event_listeners=[self.audit])
        hello = await self.client.admin.command('hello')
        self.assertEqual(self.client.address, ('127.0.0.1', 27018))
        self.assertEqual(hello['setName'], 'app_finanzas_dev_rs')
        self.assertTrue(hello['isWritablePrimary'])
        self.assertIsNotNone(hello.get('logicalSessionTimeoutMinutes'))
        self.raw = self.client[self.name]
        self.assertEqual(await self.raw.list_collection_names(), [])
        self.collections = ('accounts','categories','transactions','debts','debt_payments','bills','bill_payments',
                            'recurring_payments','recurring_payment_records','recurring_templates',
                            'saving_goals','goal_contributions','budgets','users')
        for name in self.collections:
            await self.raw.create_collection(name)
        self.db = DBProxy(self.raw, self.client)
        self.ctx = context(self.db, self.client)
        print('R3 VERIFIED NEW DB:', self.name, self._testMethodName, flush=True)

    async def asyncTearDown(self):
        try:
            for database, command, address in self.audit.events:
                self.assertIn(database, (self.name, 'admin'))
                self.assertEqual(address, ('127.0.0.1', 27018))
                self.assertNotIn(command, ('drop', 'dropDatabase'))
            print('R3 RETAINED:', self.name, 'commands:', len(self.audit.events), flush=True)
        finally:
            self.client.close()

    async def insert(self, collection, doc):
        await getattr(self.db, collection).insert_one(dict(doc, _id=doc['id']))

    async def race(self, creator, destroyer, hook, matches, after=False):
        """Pause once after a snapshot read, BEFORE the coordinated parent write.

        The delete wins deterministically. Resuming the old snapshot must cause
        a real WriteConflict and a fresh callback, rather than commit an orphan.
        """
        failed_before = len(self.audit.failures)
        entered, resume = asyncio.Event(), asyncio.Event()
        original = self.ctx.ns[hook]
        calls = 0
        task = None
        async def paused(*args, **kwargs):
            nonlocal calls
            value = await original(*args, **kwargs) if after else None
            if asyncio.current_task() is task and matches(args, kwargs):
                calls += 1
                if calls == 1:
                    entered.set()
                    await asyncio.wait_for(resume.wait(), 15)
            return value if after else await original(*args, **kwargs)
        self.ctx.ns[hook] = paused
        task = asyncio.create_task(creator())
        try:
            await asyncio.wait_for(entered.wait(),15)
            deleted = await destroyer()
            self.assertEqual(deleted.status_code,200,deleted.text)
            resume.set()
            created = await asyncio.wait_for(task,20)
            self.last_conflicts = self.audit.failures[failed_before:].count(112)
            return created, calls
        finally:
            resume.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self.ctx.ns[hook] = original

    async def test_race_recurring_expense_mark_and_link(self):
        for mode in ('expense','mark','link'):
            f = await self.fixture(recurring=True)
            payload = dict(due_date='2026-10-20',mode=mode,amount=10,account_id=f['a'])
            if mode == 'link':
                r = await self.request('POST','/transactions',dict(name='Synthetic',type='expense',amount=10,account_id=f['a']))
                self.assertEqual(r.status_code,200,r.text)
                payload['transaction_id']=r.json()['id']
            r,calls = await self.race(
                lambda: self.request('POST','/recurring-payments/'+f['rp']+'/payments',payload,'race-'+mode),
                lambda: self.request('DELETE','/recurring-payments/'+f['rp']),
                'coordinate', lambda args, kw: args[2].get('recurring_id') == f['rp'])
            self.assertEqual(r.status_code,404,(mode,r.text))
            self.assertGreater(self.last_conflicts,0,mode)
            self.assertFalse(await self.doc('recurring_payments',f['rp']))
            self.assertEqual(await self.raw.recurring_payment_records.count_documents({'recurring_id':f['rp'],'deleted':{'$ne':True}}),0)
            self.assertEqual(await self.raw.transactions.count_documents({'recurring_payment_id':f['rp']}),0)
            self.assertEqual(await self.balance(f),990 if mode=='link' else 1000)

    async def test_race_expense_with_category_and_account_delete(self):
        for field,route in (('category_id','/categories/'),('account_id','/accounts/')):
            f = await self.fixture()
            parent = f['category'] if field=='category_id' else f['a']
            payload=dict(name='Synthetic',type='expense',amount=10,**{field:parent})
            r,calls=await self.race(
                lambda: self.request('POST','/transactions',payload),
                lambda: self.request('DELETE',route+parent),
                'coordinate' if field=='category_id' else 'validate_transaction',
                (lambda args,kw:args[2].get(field)==parent) if field=='category_id' else (lambda args,kw:args[0].get(field)==parent),
                after=field=='account_id')
            self.assertEqual(r.status_code,422,r.text)
            self.assertGreater(self.last_conflicts,0)
            self.assertGreaterEqual(calls,1)
            self.assertEqual(await self.raw.transactions.count_documents({field:parent}),0)

    async def test_race_bill_create_and_edit_with_parent_delete(self):
        for method in ('POST','PUT'):
            for field,route in (('category_id','/categories/'),('account_id','/accounts/'),('recurring_payment_id','/recurring-payments/')):
                f=await self.fixture(recurring=True)
                parent=f['category'] if field=='category_id' else f['a'] if field=='account_id' else f['rp']
                payload=dict(name='Synthetic',amount=100,due_date='2026-10-20',frequency='once',**{field:parent})
                endpoint='/bills' if method=='POST' else '/bills/'+f['bill']
                r,calls=await self.race(
                    lambda: self.request(method,endpoint,payload),
                    lambda: self.request('DELETE',route+parent),
                    'coordinate',lambda args,kw: args[2].get(field)==parent)
                self.assertEqual(r.status_code,422,(method,field,r.text))
                self.assertGreater(self.last_conflicts,0)
                self.assertEqual(await self.raw.bills.count_documents({field:parent}),0)

    async def test_race_debt_create_edit_and_recurring_create_edit(self):
        for entity in ('debt','recurring'):
            for method in ('POST','PUT'):
                for field,route in (('category_id','/categories/'),('account_id','/accounts/')):
                    f=await self.fixture(recurring=True)
                    parent=f['category'] if field=='category_id' else f['a']
                    if entity=='debt':
                        payload=dict(name='Synthetic',direction='i_owe',original_amount=500,**{field:parent})
                        endpoint='/debts'+('/'+f['debt'] if method=='PUT' else '')
                        collection='debts'
                    else:
                        payload=dict(name='Synthetic',amount=100,start_date='2026-10-20',**{field:parent})
                        endpoint='/recurring-payments'+('/'+f['rp'] if method=='PUT' else '')
                        collection='recurring_payments'
                    r,calls=await self.race(
                        lambda: self.request(method,endpoint,payload),lambda: self.request('DELETE',route+parent),
                        'coordinate',lambda args,kw: args[2].get(field)==parent)
                    self.assertEqual(r.status_code,422,(entity,method,field,r.text))
                    self.assertEqual(await self.raw[collection].count_documents({field:parent}),0)

    async def test_race_debt_payment_and_bill_payment_with_parent_delete(self):
        for entity in ('debt','bill'):
            f=await self.fixture()
            if entity=='debt':
                creator=lambda: self.request('POST','/debt-payments',dict(debt_id=f['debt'],amount=10,account_id=f['a']),'race-debt')
                destroyer=lambda: self.request('DELETE','/debts/'+f['debt'])
                hook='validate_payment';match=lambda args,kw: args[0]==f['debt']
            else:
                creator=lambda: self.request('POST','/bills/'+f['bill']+'/payments',dict(amount=10,account_id=f['a']),'race-bill')
                destroyer=lambda: self.request('DELETE','/bills/'+f['bill'])
                hook='_bill_for_write';match=lambda args,kw: args[0]==f['bill']
            r,calls=await self.race(creator,destroyer,hook,match,after=entity=="debt")
            self.assertEqual(r.status_code,404,r.text)
            self.assertEqual(await self.raw.transactions.count_documents({'account_id':f['a']}),0)
            self.assertEqual(await self.balance(f),1000)

    async def test_creation_wins_parent_delete_revalidates_children(self):
        f=await self.fixture()
        # Delete reads an empty dependency snapshot; child commits first.
        entered,resume=asyncio.Event(),asyncio.Event()
        original=self.ctx.ns['db']
        real=self.raw.categories
        class PausedDB:
            def __getattr__(inner,name):
                if name!='categories': return getattr(original,name)
                class Category:
                    def __getattr__(inner2,method): return getattr(real,method)
                    async def delete_one(inner2,*args,**kwargs):
                        if not entered.is_set():
                            entered.set();await asyncio.wait_for(resume.wait(),15)
                        return await real.delete_one(*args,**kwargs)
                return Category()
        self.ctx.ns['db']=PausedDB()
        task=asyncio.create_task(self.request('DELETE','/categories/'+f['category']))
        try:
            await asyncio.wait_for(entered.wait(),15)
            made=await self.request('POST','/transactions',dict(name='Synthetic',type='expense',amount=10,category_id=f['category']))
            self.assertEqual(made.status_code,200,made.text)
            resume.set()
            deleted=await asyncio.wait_for(task,20)
            self.assertEqual(deleted.status_code,409,deleted.text)
            self.assertTrue(await self.doc('categories',f['category']))
        finally:
            resume.set();self.ctx.ns['db']=original
            if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)

    async def test_rollback_after_unlink_and_update(self):
        for entity in ('bill','recurring','debt-update'):
            f=await self.fixture(linked=True)
            await self.billpay(f)
            before=await self.snapshot()
            if entity=='debt-update':
                fail=('debts','update_one');route='/debts/'+f['debt'];method='PUT'
                data=dict(name='Edited',direction='i_owe',original_amount=500,account_id=f['a'],category_id=f['category'])
            else:
                fail=('transactions','update_many');route=('/bills/'+f['bill']) if entity=='bill' else '/recurring-payments/'+f['rp'];method='DELETE';data=None
            self.ctx.ns['db']=DBProxy(self.raw,self.client,fail)
            try:r=await self.request(method,route,data)
            finally:self.ctx.ns['db']=self.db
            self.assertEqual(r.status_code,503,r.text)
            self.assertEqual(await self.snapshot(),before)

    async def test_same_key_concurrent_and_lost_response_replay(self):
        f=await self.fixture(linked=True)
        payload=dict(amount=30,account_id=f['a'])
        responses=await asyncio.gather(*(self.request('POST','/bills/'+f['bill']+'/payments',payload,'same') for _ in range(2)))
        self.assertEqual([r.status_code for r in responses],[200,200])
        self.assertEqual(responses[0].json()['id'],responses[1].json()['id'])
        # Treat the first response as lost, then recover by replaying exact intent.
        recovered=await self.request('POST','/bills/'+f['bill']+'/payments',payload,'same')
        self.assertEqual(recovered.status_code,200,recovered.text)
        self.assertEqual(await self.raw.bill_payments.count_documents({'bill_id':f['bill'],'deleted':{'$ne':True}}),1)
        self.assertEqual(await self.raw.transactions.count_documents({'bill_id':f['bill']}),1)
        self.assertEqual(await self.balance(f),970)
        different=await self.request('POST','/bills/'+f['bill']+'/payments',dict(payload,amount=40),'same')
        self.assertEqual(different.status_code,409,different.text)

    async def test_goal_history_and_balance_preserved(self):
        f = await self.fixture()
        r = await self.request('POST','/goals',dict(name='Synthetic goal',target_amount=500,account_id=f['b']))
        self.assertEqual(r.status_code,200,r.text)
        gid = r.json()['id']
        payload = dict(kind='deposit',amount=50,real_movement=True,account_id=f['a'])
        r = await self.request('POST','/goals/'+gid+'/contributions',payload,'goal-receipt')
        self.assertEqual(r.status_code,200,r.text)
        p = r.json()['contribution']
        self.assertEqual(await self.balance(f),950)
        self.assertEqual((await self.doc('accounts',f['b']))['current_balance'],1050)
        r = await self.request('DELETE','/goals/'+gid)
        self.assertEqual(r.status_code,200,r.text)
        self.assertTrue((await self.doc('goal_contributions',p['id']))['deleted'])
        tx = await self.doc('transactions',p['transaction_id'])
        self.assertFalse(tx.get('goal_id'))
        self.assertEqual(await self.balance(f),950)
        self.assertEqual((await self.doc('accounts',f['b']))['current_balance'],1050)
        r = await self.request('POST','/goals/'+gid+'/contributions',payload,'goal-receipt')
        self.assertEqual(r.status_code,409,r.text)

    async def test_monthly_series_group_survives_root_deletion(self):
        f = await self.fixture()
        await self.change('bills',f['bill'],frequency='monthly')
        p = await self.billpay(f,amount=100)
        nxt = p['next_bill_id']
        self.assertTrue(nxt)
        r = await self.request('DELETE','/bills/'+f['bill'])
        self.assertEqual(r.status_code,200,r.text)
        r = await self.request('GET','/bills/'+nxt)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['series_id'],f['bill'])
        self.assertEqual(await self.balance(f),900)
        # Group identity does not require the original period document to exist.
        r = await self.request('POST','/bills/'+nxt+'/payments',dict(amount=100,account_id=f['a']),'next-period')
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(await self.balance(f),800)

    async def test_default_category_initialization_remains_idempotent(self):
        first = await self.request('POST','/categories/init-defaults')
        self.assertEqual(first.status_code,200,first.text)
        second = await self.request('POST','/categories/init-defaults')
        self.assertEqual(second.status_code,200,second.text)
        self.assertEqual(second.json()['created'],0)
        self.assertEqual(second.json()['groups_created'],0)
        self.assertEqual(second.json()['links'],0)
        self.assertNotIn('_reference_revision',(await self.request('GET','/categories')).text)

    async def test_race_tracking_goal_and_budget_with_parent_delete(self):
        for entity in ('goal','budget','category-child','template'):
            f = await self.fixture()
            if entity=='goal':
                endpoint='/goals';payload=dict(name='Synthetic',target_amount=100,account_id=f['a'])
                field='account_id';parent=f['a'];route='/accounts/'
            elif entity=='budget':
                endpoint='/budgets';payload=dict(name='Synthetic',amount_limit=100,category_id=f['category'],period='monthly')
                field='category_id';parent=f['category'];route='/categories/'
            elif entity=='category-child':
                endpoint='/categories';payload=dict(name='Synthetic',type='expense',parent_id=f['category'])
                field='parent_id';parent=f['category'];route='/categories/'
            else:
                tx=await self.request('POST','/transactions',dict(name='Synthetic',type='expense',amount=10,account_id=f['a']))
                parent=tx.json()['id'];field='source_transaction_id';route='/transactions/'
                endpoint='/recurring';payload=dict(name='Synthetic',amount=10,type='expense',source_transaction_id=parent)
            r,calls=await self.race(lambda:self.request('POST',endpoint,payload),
                 lambda:self.request('DELETE',route+parent),'coordinate',lambda args,kw:args[2].get(field)==parent)
            self.assertEqual(r.status_code,422,(entity,r.text))

    async def test_race_payment_account_delete(self):
        for entity in ('bill','debt'):
            f=await self.fixture()
            endpoint='/bills/'+f['bill']+'/payments' if entity=='bill' else '/debt-payments'
            payload=dict(amount=10,account_id=f['a'])
            if entity=='debt':payload['debt_id']=f['debt']
            r,calls=await self.race(lambda:self.request('POST',endpoint,payload,'account-race'),
                lambda:self.request('DELETE','/accounts/'+f['a']),
                'coordinate' if entity=='bill' else 'validate_payment',
                (lambda args,kw:args[2].get('account_id')==f['a']) if entity=='bill' else (lambda args,kw:args[2]==f['a']),
                after=entity=='debt')
            self.assertIn(r.status_code,(404,422),r.text)
            self.assertEqual(await self.raw.transactions.count_documents({'account_id':f['a']}),0)

    async def test_unknown_commit_does_not_duplicate_payment(self):
        f=await self.fixture()
        raw_client=self.client
        class UncertainSession:
            def __init__(inner,session):inner.session=session
            async def __aenter__(inner):return inner
            async def __aexit__(inner,*args):await inner.session.end_session()
            async def with_transaction(inner,operation,**kwargs):
                await inner.session.with_transaction(operation,**kwargs)
                raise OperationFailure('Synthetic commit response unavailable',details={'errorLabels':['UnknownTransactionCommitResult']})
        class UncertainClient:
            async def start_session(inner):return UncertainSession(await raw_client.start_session())
        self.ctx.ns['client']=UncertainClient()
        data=dict(amount=40,account_id=f['a'])
        try:r=await self.request('POST','/bills/'+f['bill']+'/payments',data,'uncertain')
        finally:self.ctx.ns['client']=raw_client
        self.assertEqual(r.status_code,503,r.text)
        r=await self.request('POST','/bills/'+f['bill']+'/payments',data,'uncertain')
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(await self.balance(f),960)
        self.assertEqual(await self.raw.bill_payments.count_documents({'bill_id':f['bill']}),1)
        self.assertEqual(await self.raw.transactions.count_documents({'bill_id':f['bill']}),1)

    async def test_concurrent_bidirectional_parent_unlink(self):
        f=await self.fixture(linked=True)
        p=await self.billpay(f)
        responses=await asyncio.wait_for(asyncio.gather(
            self.request('DELETE','/bills/'+f['bill']),
            self.request('DELETE','/recurring-payments/'+f['rp'])),20)
        self.assertEqual([r.status_code for r in responses],[200,200],[r.text for r in responses])
        tx=await self.doc('transactions',p['transaction_id'])
        self.assertFalse(tx.get('bill_id'))
        self.assertFalse(tx.get('recurring_payment_id'))
        self.assertTrue((await self.doc('bill_payments',p['id']))['deleted'])
        self.assertTrue((await self.doc('recurring_payment_records',p['recurring_record_id']))['deleted'])
        self.assertEqual(await self.balance(f),930)

    async def test_inverse_check_conflicts_with_concurrent_link_creation(self):
        for method in ('PUT', 'DELETE'):
            f = await self.fixture(recurring=True)
            r = await self.request('POST', '/transactions', dict(name='Synthetic', type='expense', amount=10, account_id=f['a']))
            self.assertEqual(r.status_code, 200, r.text)
            tid = r.json()['id']
            data = dict(name='Edited', type='expense', amount=20) if method=='PUT' else None
            r, calls = await self.race(
                lambda: self.request(method, '/transactions/'+tid, data),
                lambda: self.request('POST', '/recurring-payments/'+f['rp']+'/payments',
                                    dict(due_date='2026-10-20', mode='link', transaction_id=tid), 'concurrent-link'),
                'check_movement_references', lambda args, kw: args[2]['id']==tid, after=True)
            self.assertEqual(r.status_code, 409, r.text)
            self.assertGreater(self.last_conflicts, 0)
            tx = await self.doc('transactions', tid)
            rec = await self.doc('recurring_payment_records', tx['recurring_record_id'])
            self.assertEqual(tx['amount'], 10)
            self.assertEqual(rec['transaction_id'], tid)
            self.assertEqual(rec['amount'], tx['amount'])
            self.assertEqual(await self.balance(f), 990)
            self.assertEqual(await self.raw.transactions.count_documents({'id':tid}), 1)

    async def test_link_creation_revalidates_after_ordinary_write_wins(self):
        for method in ('PUT', 'DELETE'):
            f = await self.fixture(recurring=True)
            r = await self.request('POST', '/transactions', dict(name='Synthetic', type='expense', amount=10, account_id=f['a']))
            self.assertEqual(r.status_code, 200, r.text)
            tid = r.json()['id']
            data = dict(name='Edited', type='expense', amount=20) if method=='PUT' else None
            r, calls = await self.race(
                lambda: self.request('POST', '/recurring-payments/'+f['rp']+'/payments',
                                    dict(due_date='2026-10-20', mode='link', transaction_id=tid), 'concurrent-link'),
                lambda: self.request(method, '/transactions/'+tid, data),
                'coordinate', lambda args, kw: args[2].get('account_id')==f['a'])
            self.assertGreater(self.last_conflicts, 0)
            if method=='DELETE':
                self.assertEqual(r.status_code, 422, r.text)
                self.assertIsNone(await self.doc('transactions', tid))
                self.assertEqual(await self.raw.recurring_payment_records.count_documents({'transaction_id':tid}), 0)
                self.assertEqual(await self.balance(f), 1000)
            else:
                self.assertEqual(r.status_code, 200, r.text)
                tx = await self.doc('transactions', tid)
                self.assertEqual(tx['amount'], 20)
                self.assertEqual(r.json()['amount'], 20)
                self.assertEqual(tx['recurring_record_id'], r.json()['id'])
                self.assertEqual(await self.balance(f), 980)
