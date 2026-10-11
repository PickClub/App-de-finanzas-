"""Ordinary financial writes: isolated transaction rollback/retry regressions."""
import asyncio
import copy
import unittest
from pymongo.errors import OperationFailure
from backend.tests import test_payment_consistency as harness


class OrdinaryAtomicityTests(unittest.IsolatedAsyncioTestCase):
    setUp = harness.PaymentTests.setUp
    request = harness.PaymentTests.request
    balance = harness.PaymentTests.balance
    created = harness.PaymentTests.created
    pay = harness.PaymentTests.pay
    active_payments = harness.PaymentTests.active_payments

    def movement(self, **changes):
        payload = dict(name="Synthetic", type="expense", amount=100, account_id="a")
        payload.update(changes)
        return payload

    async def add(self, **changes):
        r = await self.request("POST", "/transactions", json=self.movement(**changes))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    async def test_creation_failure_rolls_back(self):
        for write in (1, 2):
            self.setUp()
            before = copy.deepcopy(self.db.data)
            self.db.fail_at = write
            r = await self.request("POST", "/transactions", json=self.movement())
            self.assertEqual(r.status_code, 503, r.text)
            self.assertEqual(self.db.data, before)

    async def test_edit_and_delete_failure_roll_back(self):
        for method in ("PUT", "DELETE"):
            tx = await self.add()
            before = copy.deepcopy(self.db.data)
            self.db.fail_at = self.db.writes + 2
            args = {"json": self.movement(amount=200)} if method == "PUT" else {}
            r = await self.request(method, f"/transactions/{tx['id']}", **args)
            self.assertEqual(r.status_code, 503, r.text)
            self.assertEqual(self.db.data, before)
            self.db.fail_at = None

    async def test_transfer_failures_roll_back_each_write(self):
        for method in ("POST", "PUT", "DELETE"):
            for failure in (1, 2, 3):
                self.setUp()
                tx = await self.add(type="transfer", to_account_id="b") if method != "POST" else None
                before = copy.deepcopy(self.db.data)
                self.db.fail_at = self.db.writes + failure
                path = "/transactions" + (f"/{tx['id']}" if tx else "")
                args = {"json": self.movement(type="transfer", to_account_id="b", amount=200)} if method != "DELETE" else {}
                r = await self.request(method, path, **args)
                self.assertEqual(r.status_code, 503, r.text)
                self.assertEqual(self.db.data, before)

    async def test_transfer_lifecycle_and_move_between_accounts(self):
        tx = await self.add(type="transfer", to_account_id="b")
        self.assertEqual((self.balance(), self.balance("b")), (900, 600))
        r = await self.request("PUT", f"/transactions/{tx['id']}", json=self.movement(type="transfer", to_account_id="b", amount=200))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((self.balance(), self.balance("b")), (800, 700))
        self.assertEqual((await self.request("DELETE", f"/transactions/{tx['id']}")).status_code, 200)
        self.assertEqual((self.balance(), self.balance("b")), (1000, 500))
        tx = await self.add()
        r = await self.request("PUT", f"/transactions/{tx['id']}", json=self.movement(account_id="b"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((self.balance(), self.balance("b")), (1000, 400))

    async def test_move_between_accounts_rolls_back_both_balances(self):
        for failure in (2, 3):
            self.setUp()
            tx = await self.add()
            before = copy.deepcopy(self.db.data)
            self.db.fail_at = self.db.writes + failure
            r = await self.request("PUT", f"/transactions/{tx['id']}", json=self.movement(account_id="b"))
            self.assertEqual(r.status_code, 503, r.text)
            self.assertEqual(self.db.data, before)

    async def test_account_change_failure_rolls_back(self):
        for write in (1, 2):
            self.setUp()
            await self.add()
            before = copy.deepcopy(self.db.data)
            self.db.fail_at = self.db.writes + write
            r = await self.request("PUT", "/accounts/a", json={"name": "Renamed", "initial_balance": 2000})
            self.assertEqual(r.status_code, 503, r.text)
            self.assertEqual(self.db.data, before)

    async def test_simultaneous_expenses_end_at_800(self):
        await asyncio.gather(self.add(), self.add())
        self.assertEqual(len(self.db.data["transactions"]), 2)
        self.assertEqual(self.balance(), 800)

    async def test_account_change_and_expense_are_serializable(self):
        movement, account = await asyncio.gather(
            self.add(), self.request("PUT", "/accounts/a", json={"name": "Changed", "initial_balance": 2000}))
        self.assertEqual(account.status_code, 200, account.text)
        self.assertEqual(self.balance(), 1900)

    async def test_debt_payment_and_account_change_are_serializable(self):
        payment, account = await asyncio.gather(
            self.created(), self.request("PUT", "/accounts/a", json={"name": "Changed", "initial_balance": 2000}))
        self.assertEqual(account.status_code, 200, account.text)
        self.assertEqual(self.balance(), 1900)
        self.assertEqual(len(self.active_payments()), 1)

    async def test_transient_conflict_retries_but_is_bounded(self):
        original = self.ns["recompute_account_balance"]
        calls = []
        async def conflict(*args, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise OperationFailure("WriteConflict", code=112, details={"errorLabels": ["TransientTransactionError"]})
            return await original(*args, **kwargs)
        self.ns["recompute_account_balance"] = conflict
        tx = await self.add()
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(self.db.data["transactions"]), 1)
        self.assertEqual(self.balance(), 900)
        calls.clear()
        async def always_conflict(*args, **kwargs):
            calls.append(1)
            raise OperationFailure("WriteConflict", code=112, details={"errorLabels": ["TransientTransactionError"]})
        self.ns["recompute_account_balance"] = always_conflict
        before = copy.deepcopy(self.db.data)
        r = await self.request("POST", "/transactions", json=self.movement())
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.db.data, before)

    async def test_unknown_commit_does_not_replay_creation(self):
        self.db.commit_then_error = True
        r = await self.request("POST", "/transactions", json=self.movement())
        self.assertEqual(r.status_code, 503, r.text)
        self.assertEqual(len(self.db.data["transactions"]), 1)
        self.assertEqual(self.db.writes, 2)
        self.assertEqual(self.balance(), 900)

    async def test_unknown_commit_does_not_replay_edit_or_delete(self):
        for method in ("PUT", "DELETE"):
            self.setUp()
            tx = await self.add()
            self.db.writes = 0
            self.db.commit_then_error = True
            args = {"json": self.movement(amount=200)} if method == "PUT" else {}
            r = await self.request(method, f"/transactions/{tx['id']}", **args)
            self.assertEqual(r.status_code, 503, r.text)
            self.assertEqual(self.db.writes, 2)
            self.assertEqual(self.balance(), 800 if method == "PUT" else 1000)
            self.assertEqual(len(self.db.data["transactions"]), 1 if method == "PUT" else 0)

    async def test_unknown_commit_label_takes_precedence_over_transient_label(self):
        class AmbiguousCommit(harness.TransactionContext):
            async def __aexit__(self, kind, error, traceback):
                result = await super().__aexit__(kind, error, traceback)
                if kind is None:
                    raise OperationFailure("Ambiguous commit", details={"errorLabels": [
                        "UnknownTransactionCommitResult", "TransientTransactionError"
                    ]})
                return result
        class AmbiguousSession(harness.Session):
            def start_transaction(self, **options):
                return AmbiguousCommit(self)
        class AmbiguousClient(harness.Client):
            async def start_session(self):
                return AmbiguousSession(self.database)
        self.ns["client"] = AmbiguousClient(self.db)
        r = await self.request("POST", "/transactions", json=self.movement())
        self.assertEqual(r.status_code, 503, r.text)
        self.assertEqual(len(self.db.data["transactions"]), 1)
        self.assertEqual(self.db.writes, 2)
        self.assertEqual(self.balance(), 900)

    async def test_unconfirmed_noncommitted_operation_leaves_no_partial_writes(self):
        self.db.fail_commit = True
        before = copy.deepcopy(self.db.data)
        r = await self.request("POST", "/transactions", json=self.movement())
        self.assertEqual(r.status_code, 503, r.text)
        self.assertEqual(self.db.data, before)

    async def test_unsupported_transactions_never_write(self):
        tx = await self.add()
        self.client.supported = False
        before = copy.deepcopy(self.db.data)
        for method, path, args in (
            ("POST", "/transactions", {"json": self.movement()}),
            ("PUT", f"/transactions/{tx['id']}", {"json": self.movement(amount=200)}),
            ("DELETE", f"/transactions/{tx['id']}", {}),
            ("PUT", "/accounts/a", {"json": {"name": "Changed", "initial_balance": 2000}}),
        ):
            r = await self.request(method, path, **args)
            self.assertEqual(r.status_code, 503, r.text)
            self.assertEqual(self.db.data, before)
