"""Loans and C4 legacy type key coverage; synthetic memory only."""
from types import SimpleNamespace
import unittest
from backend.history_keys import inspect_history_keys
from backend.tests import test_ordinary_history_keys as ordinary


class LoanKeyCoverageTests(unittest.IsolatedAsyncioTestCase):
    request=ordinary.OrdinaryKeyCases.request
    payload=ordinary.OrdinaryKeyCases.payload
    add=ordinary.OrdinaryKeyCases.add
    edit=ordinary.OrdinaryKeyCases.edit
    stored=ordinary.OrdinaryKeyCases.stored
    balance=ordinary.OrdinaryKeyCases.balance
    snapshot=ordinary.OrdinaryKeyCases.snapshot
    setUp=ordinary.OrdinaryKeyMemoryTests.setUp

    async def legacy(self,keys=True,date=None):
        if not keys:self.ns['settings']=SimpleNamespace(history_keys_write_enabled=False)
        p=await self.add(**({'date':date} if date else {}))
        row=next(r for r in self.db.data['transactions'] if r['id']==p['id'])
        # Synthetic setup, never real data. Type is not a source of history keys.
        row['type']='legacy_unknown'
        self.ns['settings']=SimpleNamespace(history_keys_write_enabled=True,history_keys_generation=1)
        return p

    async def test_post_and_put_both_loans_sources_and_balances(self):
        for kind in ('loan_given','loan_received'):
            p=await self.add(type=kind)
            before=await self.stored(p['id'])
            self.assertEqual(inspect_history_keys(before,1),'ready')
            await self.edit(p['id'],type=kind,amount=80,date='2026-W40-5T23:59:59.999999Z')
            final=await self.stored(p['id'])
            self.assertEqual(inspect_history_keys(final,1),'ready')
            self.assertNotEqual(before['_history_keys'],final['_history_keys'])
            self.assertEqual((final['id'],final['user_id'],final['amount'],final['date']),(p['id'],'default-user',80,'2026-W40-5T23:59:59.999999Z'))
        self.assertEqual(await self.balance(),1000)

    async def test_expense_to_loan_sources_recomputed(self):
        p=await self.add()
        await self.edit(p['id'],type='loan_given',amount=120,date='2026-11-01')
        self.assertEqual(inspect_history_keys(await self.stored(p['id']),1),'ready')
        self.assertEqual(await self.balance(),880)
        await self.edit(p['id'],type='loan_received',amount=150,date='2026-11-02')
        self.assertEqual(inspect_history_keys(await self.stored(p['id']),1),'ready')
        self.assertEqual(await self.balance(),1150)

    async def test_type_only_change_keeps_keys_and_existing_balance_rules(self):
        p=await self.add()
        keys=(await self.stored(p['id']))['_history_keys']
        for kind,balance in (('loan_given',900),('loan_received',1100),('income',1100)):
            await self.edit(p['id'],type=kind)
            row=await self.stored(p['id'])
            self.assertEqual(row['_history_keys'],keys)
            self.assertEqual(inspect_history_keys(row,1),'ready')
            self.assertEqual(await self.balance(),balance)

    async def test_legacy_type_unchanged_source_edits_recompute(self):
        p=await self.legacy()
        await self.edit(p['id'],type='legacy_unknown',amount=90,date='2026-11-01')
        row=await self.stored(p['id'])
        self.assertEqual(row['type'],'legacy_unknown')
        self.assertEqual(inspect_history_keys(row,1),'ready')
        self.assertEqual(await self.balance(),1000)
        await self.edit(p['id'],type='legacy_unknown',amount=90,date='invalid-date')
        self.assertEqual(inspect_history_keys(await self.stored(p['id']),1),'unverifiable')

    async def test_legacy_missing_admin_omitted_null_does_not_backfill(self):
        p=await self.legacy(keys=False)
        r=await self.request('PUT','/transactions/'+p['id'],json={'name':'Renamed','type':'legacy_unknown','amount':100,'notes':None})
        self.assertEqual(r.status_code,200,r.text)
        self.assertNotIn('_history',r.text)
        row=await self.stored(p['id'])
        self.assertEqual(inspect_history_keys(row,1),'missing')
        self.assertEqual(row['date'],p['date'])
        self.assertIsNone(row['notes'])
        await self.edit(p['id'],type='legacy_unknown',amount=80)
        self.assertEqual(inspect_history_keys(await self.stored(p['id']),1),'ready')

    async def test_unknown_new_types_still_rejected_no_writes(self):
        before=await self.snapshot()
        r=await self.request('POST','/transactions',json=self.payload(type='unsupported_new'))
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(await self.snapshot(),before)
        p=await self.legacy()
        before=await self.snapshot()
        r=await self.request('PUT','/transactions/'+p['id'],json=self.payload(type='different_unknown'))
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(await self.snapshot(),before)

    async def test_disabled_sources_stale_and_reenable_admin_no_repair(self):
        p=await self.add(type='loan_given')
        self.ns['settings']=SimpleNamespace(history_keys_write_enabled=False)
        await self.edit(p['id'],type='loan_given',amount=80,date='2026-11-01')
        self.assertEqual(inspect_history_keys(await self.stored(p['id']),1),'stale_or_corrupt')
        self.ns['settings']=SimpleNamespace(history_keys_write_enabled=True,history_keys_generation=1)
        await self.edit(p['id'],type='loan_given',amount=80,date='2026-11-01',notes='admin')
        self.assertEqual(inspect_history_keys(await self.stored(p['id']),1),'stale_or_corrupt')
        await self.edit(p['id'],type='loan_given',amount=70,date='2026-11-01')
        self.assertEqual(inspect_history_keys(await self.stored(p['id']),1),'ready')

    async def test_disabled_creation_and_admin_type_change_stays_missing(self):
        self.ns['settings']=SimpleNamespace(history_keys_write_enabled=False)
        p=await self.add(type='loan_received')
        await self.edit(p['id'],type='loan_received',amount=80)
        self.assertEqual(inspect_history_keys(await self.stored(p['id']),1),'missing')
        self.ns['settings']=SimpleNamespace(history_keys_write_enabled=True,history_keys_generation=1)
        await self.edit(p['id'],type='income',amount=80)
        self.assertEqual(inspect_history_keys(await self.stored(p['id']),1),'missing')

    async def test_loan_rollback_after_keys_and_balance(self):
        original=self.ns['recompute_account_balance']
        from unittest.mock import patch
        from pymongo.errors import OperationFailure
        async def fail(*args,**kwargs):
            await original(*args,**kwargs)
            raise OperationFailure('Synthetic after loan keys and balance')
        before=await self.snapshot()
        with patch.dict(self.ns,{'recompute_account_balance':fail}):
            r=await self.request('POST','/transactions',json=self.payload(type='loan_given'))
            self.assertEqual(r.status_code,503,r.text)
        self.assertEqual(await self.snapshot(),before)
        p=await self.add(type='loan_received')
        before=await self.snapshot()
        with patch.dict(self.ns,{'recompute_account_balance':fail}):
            r=await self.request('PUT','/transactions/'+p['id'],json=self.payload(type='loan_received',amount=80))
            self.assertEqual(r.status_code,503,r.text)
        self.assertEqual(await self.snapshot(),before)
