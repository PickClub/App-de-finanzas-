"""C4 and omitted-field regressions: AST routes and an in-memory DB only."""
import copy
import unittest

from backend.tests import test_payment_consistency as harness


class OrdinaryCollection(harness.Collection):
    def before_write(self, session):
        if session is not None:
            return super().before_write(session)
        self.database.writes += 1

    async def insert_one(self, doc, *, session=None):
        if "_id" in doc:
            return await super().insert_one(doc, session=session)
        self.before_write(session)
        self.docs(session).append(copy.deepcopy(doc))


class OrdinaryDatabase(harness.Database):
    def __getattr__(self, name):
        if name in self.data:
            return OrdinaryCollection(self, name)
        raise AttributeError(name)


class TransactionValidationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        harness.PaymentTests.setUp(self)
        database = OrdinaryDatabase()
        database.data = self.db.data
        self.db = database
        self.client = harness.Client(database)
        self.ns.update(db=database, client=self.client)

    request = harness.PaymentTests.request
    balance = harness.PaymentTests.balance
    created = harness.PaymentTests.created
    pay = harness.PaymentTests.pay
    active_payments = harness.PaymentTests.active_payments

    def payload(self, **changes):
        return dict(name="Movement", amount=25, type="expense", account_id="a", **changes)

    async def add(self, **changes):
        data = self.payload()
        data.update(changes)
        response = await self.request("POST", "/transactions", json=data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_valid_types_and_optional_accounts(self):
        for kind in ("income", "loan_given", "loan_received"):
            tx = await self.add(type=kind, account_id=None)
            self.assertIsNone(tx["account_id"])
            await self.add(type=kind, account_id="a", category_id="category")
        self.assertEqual((await self.request("POST", "/transactions", json={
            "name": "Payment", "amount": 10, "type": "debt_payment"
        })).status_code, 409)
        await self.created()

    async def test_invalid_new_amounts_and_types_do_not_write(self):
        for field, values in (("amount", (0, -1, "NaN", "Infinity", "-Infinity")),
                              ("type", ("unknown", "", "EXPENSE"))):
            for value in values:
                with self.subTest(field=field, value=value):
                    before = copy.deepcopy(self.db.data)
                    data = self.payload()
                    data[field] = value
                    response = await self.request("POST", "/transactions", json=data)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(self.db.data, before)

    async def test_invalid_edits_do_not_write(self):
        tx = await self.add(account_id="a")
        for field, value in (("amount", 0), ("amount", -1), ("amount", "NaN"),
                             ("amount", "Infinity"), ("type", "unknown"),
                             ("account_id", "missing"), ("category_id", "missing"),
                             ("to_account_id", "b")):
            before = copy.deepcopy(self.db.data)
            data = self.payload()
            data[field] = value
            r = await self.request("PUT", f"/transactions/{tx['id']}", json=data)
            self.assertEqual(r.status_code, 422, r.text)
            self.assertEqual(self.db.data, before)

    async def test_reference_ownership_and_existence(self):
        self.db.data["accounts"].append(dict(id="foreign", user_id="other"))
        self.db.data["categories"].append(dict(id="foreign", user_id="other"))
        for field in ("account_id", "category_id", "to_account_id"):
            for value in ("missing", "foreign", ""):
                before = copy.deepcopy(self.db.data)
                data = self.payload()
                data[field] = value
                self.assertEqual((await self.request("POST", "/transactions", json=data)).status_code, 422)
                self.assertEqual(self.db.data, before)

    async def test_transfer_valid_balances(self):
        tx = await self.add(type="transfer", account_id="a", to_account_id="b")
        self.assertEqual((self.balance("a"), self.balance("b")), (975, 525))
        data = dict(name="Renamed", amount=25, type="transfer")
        r = await self.request("PUT", f"/transactions/{tx['id']}", json=data)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["account_id"], r.json()["to_account_id"]), ("a", "b"))
        self.assertEqual((self.balance("a"), self.balance("b")), (975, 525))

    async def test_invalid_transfers_do_not_write(self):
        for source, target in ((None, None), ("a", None), (None, "b"), ("a", "a"),
                               ("missing", "b"), ("a", "missing")):
            before = copy.deepcopy(self.db.data)
            data = dict(name="Transfer", amount=25, type="transfer", account_id=source, to_account_id=target)
            self.assertEqual((await self.request("POST", "/transactions", json=data)).status_code, 422)
            self.assertEqual(self.db.data, before)
        tx = await self.add(type="transfer", account_id="a", to_account_id="b")
        for changes in ({"account_id": None}, {"to_account_id": None}, {"to_account_id": "a"}):
            before = copy.deepcopy(self.db.data)
            data = dict(name="Transfer", amount=25, type="transfer", **changes)
            self.assertEqual((await self.request("PUT", f"/transactions/{tx['id']}", json=data)).status_code, 422)
            self.assertEqual(self.db.data, before)

    async def test_omitted_ordinary_fields_preserved(self):
        tx = await self.add(account_id="a", category_id="category", notes="Keep", date="2026-01-01")
        r = await self.request("PUT", f"/transactions/{tx['id']}", json={"name": "Renamed", "amount": 25, "type": "expense"})
        self.assertEqual(r.status_code, 200, r.text)
        for field in ("account_id", "category_id", "notes", "date"):
            self.assertEqual(r.json()[field], tx[field])
        self.assertEqual(self.balance(), 975)

    async def test_explicit_null_income_optional_relations(self):
        tx = await self.add(type="income", account_id="a", category_id="category", notes="Clear")
        r = await self.request("PUT", f"/transactions/{tx['id']}", json={
            "name": "Movement", "amount": 25, "type": "income",
            "account_id": None, "category_id": None, "notes": None,
        })
        self.assertEqual(r.status_code, 200, r.text)
        for field in ("account_id", "category_id", "notes"):
            self.assertIsNone(r.json()[field])
        self.assertEqual(self.balance(), 1000)

    async def test_legacy_fields_preserved_and_invalid_replacements_rejected(self):
        for field, value, replacement in (("amount", -10, -20), ("amount", 0, -1),
                ("type", "legacy", "another-unknown"), ("account_id", "missing", "other-missing"),
                ("category_id", "missing", "other-missing"), ("to_account_id", "missing", "b")):
            self.setUp()
            tx = await self.add()
            stored = self.db.data["transactions"][0]
            stored[field] = value
            data = dict(name="Metadata edit", amount=stored["amount"], type=stored["type"])
            r = await self.request("PUT", f"/transactions/{tx['id']}", json=data)
            if field == "account_id":
                self.assertEqual(r.status_code, 422, r.text)
                self.assertEqual(self.db.data["transactions"][0][field], value)
                continue
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()[field], value)
            data[field] = replacement
            before = copy.deepcopy(self.db.data)
            r = await self.request("PUT", f"/transactions/{tx['id']}", json=data)
            self.assertEqual(r.status_code, 422, r.text)
            self.assertEqual(self.db.data, before)

    async def test_legacy_invalid_transfer_preserved_until_accounts_change(self):
        tx = await self.add(type="transfer", account_id="a", to_account_id="b")
        self.db.data["transactions"][0]["to_account_id"] = "missing"
        data = dict(name="Metadata", amount=25, type="transfer")
        r = await self.request("PUT", f"/transactions/{tx['id']}", json=data)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["to_account_id"], "missing")
        data["account_id"] = "b"
        before = copy.deepcopy(self.db.data)
        self.assertEqual((await self.request("PUT", f"/transactions/{tx['id']}", json=data)).status_code, 422)
        self.assertEqual(self.db.data, before)
        data.update(account_id="a", to_account_id="b")
        self.assertEqual((await self.request("PUT", f"/transactions/{tx['id']}", json=data)).status_code, 200)

    async def test_legacy_invalid_fields_can_be_corrected(self):
        tx = await self.add()
        self.db.data["transactions"][0].update(amount=-10, type="old", account_id="missing", category_id="missing")
        data = dict(name="Corrected", amount=10, type="income", account_id="a", category_id="category")
        r = await self.request("PUT", f"/transactions/{tx['id']}", json=data)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.balance(), 1010)

    async def test_linked_payment_omission_keeps_900_balance(self):
        p = await self.created()
        self.assertEqual(self.balance(), 900)
        r = await self.request("PUT", f"/transactions/{p['transaction_id']}", json={
            "name": "Description only", "amount": 100, "type": "debt_payment",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.balance(), 900)
        self.assertEqual(r.json()["account_id"], "a")
        self.assertEqual(self.active_payments()[0]["account_id"], "a")
        self.assertEqual(r.json()["debt_payment_id"], p["id"])
        self.assertEqual(r.json()["debt_id"], "d")

    async def test_linked_payment_omitted_category_notes_date_preserved(self):
        p = await self.created()
        tx = self.db.data["transactions"][0]
        tx.update(category_id="category", notes="Keep")
        self.db.data["debt_payments"][0]["notes"] = "Keep"
        r = await self.request("PUT", f"/transactions/{p['transaction_id']}", json={
            "name": "Renamed", "amount": 100, "type": tx["type"],
        })
        self.assertEqual(r.status_code, 200, r.text)
        for field in ("category_id", "notes", "date"):
            self.assertEqual(r.json()[field], tx[field])
        self.assertEqual(self.active_payments()[0]["notes"], "Keep")

    async def test_linked_payment_explicit_null_keeps_debt_link(self):
        p = await self.created()
        r = await self.request("PUT", f"/transactions/{p['transaction_id']}", json={
            "name": "Unassigned", "amount": 100, "type": "debt_payment", "account_id": None,
            "category_id": None, "notes": None, "debt_id": None,
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["account_id"])
        self.assertEqual(self.balance(), 1000)
        self.assertEqual(r.json()["debt_id"], "d")
        self.assertEqual(r.json()["debt_payment_id"], p["id"])
        self.assertEqual(self.active_payments()[0]["debt_id"], "d")

    async def test_linked_payment_invalid_edits_rollback(self):
        p = await self.created()
        for changes in ({"amount": -1}, {"type": "expense"}, {"debt_id": "missing"},
                         {"account_id": "missing"}, {"category_id": "missing"}, {"to_account_id": "b"}):
            before = copy.deepcopy(self.db.data)
            data = dict(name="Invalid", amount=100, type="debt_payment")
            data.update(changes)
            r = await self.request("PUT", f"/transactions/{p['transaction_id']}", json=data)
            self.assertIn(r.status_code, (404, 409, 422), r.text)
            self.assertEqual(self.db.data, before)
