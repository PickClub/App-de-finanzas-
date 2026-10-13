"""Production contract and public boundaries; offline only, no server startup."""
import ast
import copy
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from bson.decimal128 import Decimal128
from backend import history_keys as keys
from backend.experiments import test_c3_history_keys_contract as approved
from backend.shared_obligations import public_financial_document
from backend.reference_integrity import public as reference_public
from backend.tests import test_payment_consistency as memory
from backend.tests import test_transaction_history as history
from backend.tests import test_shared_dispatch as dispatch

ROOT = Path(__file__).resolve().parents[1]


class ProductionContract(approved.HistoryKeysContract):
    """Run all 25 approved cases against production helpers, without editing them."""
    def setUp(self):
        def inspect(row, metadata):
            doc = {**row, "_history_keys": metadata}
            if metadata is None:
                doc.pop("_history_keys")
            return keys.inspect_history_keys(doc, 1)
        for name, function in (("source_fingerprint", keys.source_fingerprint),
                               ("build_keys", lambda row: keys.derive_history_keys(row, 1)),
                               ("inspect_keys", inspect), ("public_model", keys.strip_history_metadata)):
            p = patch.object(approved, name, function)
            p.start()
            self.addCleanup(p.stop)


class HelperTests(unittest.TestCase):
    def test_generation_explicit_and_validated(self):
        row = approved.fixture()
        self.assertEqual(keys.derive_history_keys(row, 7)["generation"], 7)
        for generation in (None, True, 0, -1, "1", 1.0):
            with self.assertRaises(ValueError):
                keys.derive_history_keys(row, generation)

    def test_with_keys_is_copy_preserves_sources_and_original_intent(self):
        row = approved.fixture(_shared_intent={"payload": {"date": None, "amount": 70}}, request_fingerprint="original")
        before = copy.deepcopy(row)
        result = keys.with_history_keys(row, 1)
        self.assertEqual(row, before)
        self.assertEqual({k: v for k, v in result.items() if k != "_history_keys"}, before)
        self.assertEqual(keys.inspect_history_keys(result, 1), "ready")

    def test_administrative_edit_does_not_adopt_missing_or_repair_obsolete_keys(self):
        for row in (approved.fixture(), approved.fixture(_history_keys={"version": 99})):
            self.assertEqual(keys.history_update_fields(row, {**row, "notes": "changed", "account_id": "B", "_reference_revision": 3}, 1), {})

    def test_effective_changes_update_only_private_fragment(self):
        row = approved.fixture()
        for final in ({**row, "amount": 71}, {**row, "date": None}, {**row, "date": "2026-10-02"}):
            before = copy.deepcopy(final)
            fragment = keys.history_update_fields(row, final, 1)
            self.assertEqual(set(fragment), {"_history_keys"})
            self.assertEqual(fragment["_history_keys"], keys.derive_history_keys(final, 1))
            self.assertEqual(final, before)

    def test_unencodable_sources_unchanged_administrative_update(self):
        row = approved.fixture(date=["invalid legacy"])
        self.assertEqual(keys.history_update_fields(row, {**row, "notes": "changed"}, 1), {})
        fragment = keys.history_update_fields(row, {**row, "date": "2026-10-01"}, 1)
        self.assertEqual(fragment["_history_keys"]["state"], "ready")

    def test_present_null_metadata_is_incompatible_not_missing(self):
        self.assertEqual(keys.inspect_history_keys(approved.fixture(_history_keys=None), 1), "incompatible")

    def test_shared_and_reference_sanitizers_recursive_and_no_mutation(self):
        value = {"id": "original", "date": "20261001", "amount": 70.0001,
                 "_history_keys": {"amount": Decimal128("70.0001")},
                 "recovery": [{"payload": {"date": None}, "_history_debug": {"secret": "synthetic"}}]}
        before = copy.deepcopy(value)
        expected = {"id": "original", "date": "20261001", "amount": 70.0001,
                    "recovery": [{"payload": {"date": None}}]}
        self.assertEqual(public_financial_document(value), expected)
        self.assertEqual(reference_public(value), expected)
        self.assertEqual(value, before)

    def test_budget_nested_transactions_use_actual_serializer(self):
        tree = ast.parse((ROOT / "server.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_public")
        ns = {"shared_public": public_financial_document}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<actual budget serializer>", "exec"), ns)
        row = {"id": "budget", "spent": 70, "_matched": [approved.fixture(_history_keys={"amount": Decimal128("70")}, _history_extra="hidden", _dt="private")], "_scope": ["category"]}
        before = copy.deepcopy(row)
        result = ns["_public"](row, with_tx=True)
        self.assertEqual(result["transactions"], [approved.fixture()])
        self.assertEqual((result["id"], result["spent"]), ("budget", 70))
        self.assertEqual(row, before)

    def test_public_and_internal_projection_separated(self):
        tree = ast.parse((ROOT / "server.py").read_text())
        ns = {"HISTORY_PUBLIC_PROJECTION": keys.PUBLIC_PROJECTION}
        nodes = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"PROJ", "INTERNAL_PROJ"} for t in n.targets)]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<actual projections>", "exec"), ns)
        self.assertEqual(ns["PROJ"]["_history_keys"], 0)
        self.assertNotIn("_history_keys", ns["INTERNAL_PROJ"])

    def test_no_generator_connected_to_financial_endpoints(self):
        helpers = {"derive_history_keys", "with_history_keys", "history_update_fields", "source_fingerprint", "inspect_history_keys"}
        for path in (ROOT / "server.py", ROOT / "shared_obligations.py", ROOT / "reference_integrity.py"):
            tree = ast.parse(path.read_text())
            for function in (n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
                for call in (n for n in ast.walk(function) if isinstance(n, ast.Call)):
                    name = call.func.id if isinstance(call.func, ast.Name) else call.func.attr if isinstance(call.func, ast.Attribute) else None
                    if name in helpers:
                        self.assertEqual(path.name, "server.py")
                        self.assertIn(function.name, {"create_transaction", "update_transaction", "create_debt_payment", "edit_payment_movement", "pay_bill", "create_goal_contribution"})
                        self.assertIn(name, {"with_history_keys", "history_update_fields"})

    def test_import_does_not_connect_load_environment_or_import_experiments(self):
        script = '''
import sys
from unittest.mock import patch
with patch("pymongo.MongoClient", side_effect=AssertionError("client forbidden")), patch("dotenv.dotenv_values", side_effect=AssertionError("dotenv forbidden")):
 import backend.history_keys
 assert not any(n.startswith("backend.experiments") for n in sys.modules)
 assert "backend.server" not in sys.modules
'''
        subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT.parent, check=True, capture_output=True, text=True)

    def test_transaction_handlers_and_financial_paths_unchanged_except_public_wrappers(self):
        required = {
            "payment_transaction": "61318560a6ce5c6378a380d20b54832f10e08e15b129501708fd27d89aa3dd48",
            "ordinary_transaction": "66920ed2bf165fcd585a5381fa6b4fafbb7023a28ccf1e71e327e28b4054a97f",
            "_public": "0993ca3f09c7bc931c98079653cc684c76d7d06aa1ac327580303e53c42457a8"}
        class RemovePublicWrapper(ast.NodeTransformer):
            def visit_Call(self, node):
                node = self.generic_visit(node)
                if isinstance(node.func, ast.Name) and node.func.id == "shared_public" and len(node.args) == 1 and not node.keywords:
                    return node.args[0]
                return node
        tree = ast.parse((ROOT / "server.py").read_text())
        for name, digest in required.items():
            node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
            actual = hashlib.sha256(ast.dump(RemovePublicWrapper().visit(node)).encode()).hexdigest()
            self.assertEqual(actual, digest, name)


class PublicHistoryRoutes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        history.TransactionHistoryTests.setUp(self)
        self.collection.rows = [approved.fixture(_history_keys={"amount": Decimal128("70")}, _history_debug="hidden")]

    request = history.TransactionHistoryTests.request

    async def test_list_page_and_detail_no_exposure_or_mutation(self):
        before = copy.deepcopy(self.collection.rows)
        for path in ("/transactions", "/transactions/page", "/transactions/tx-a"):
            response = await self.request(path)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn("_history", response.text)
            self.assertIn("2026-10-01T12:00:00Z", response.text)
        self.assertEqual(self.collection.rows, before)


class PublicMovementWrites(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        memory.PaymentTests.setUp(self)

    request = memory.PaymentTests.request
    balance = memory.PaymentTests.balance
    pay = memory.PaymentTests.pay

    async def test_normal_create_does_not_store_keys(self):
        response = await self.request("POST", "/transactions", json={"name": "Synthetic", "amount": 25, "type": "expense", "account_id": "a"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("_history_keys", self.db.data["transactions"][0])
        self.assertEqual(self.balance(), 975)

    async def test_create_public_boundary_sanitizes_even_internal_result(self):
        async def result_without_writes(operation):
            return approved.fixture(_history_keys={"amount": Decimal128("70")}, _history_debug="hidden")
        self.ns["ordinary_transaction"] = result_without_writes
        response = await self.request("POST", "/transactions", json={"name": "Synthetic", "amount": 25, "type": "expense"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("_history", response.text)
        self.assertEqual(self.db.writes, 0)

    async def test_ordinary_update_sanitizes_without_maintaining_keys(self):
        response = await self.request("POST", "/transactions", json={"name": "Synthetic", "amount": 25, "type": "expense", "account_id": "a"})
        tid = response.json()["id"]
        self.db.data["transactions"][0].update(_history_keys={"fixture": "unchanged"}, _history_debug="hidden")
        response = await self.request("PUT", "/transactions/" + tid, json={"name": "Edited", "amount": 30, "type": "expense", "account_id": "a"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("_history", response.text)
        self.assertEqual(self.db.data["transactions"][0]["_history_keys"], {"fixture": "unchanged"})
        self.assertEqual(self.balance(), 970)

    async def test_debt_movement_update_and_retry_receipt_preserved(self):
        response = await self.pay(key="original")
        self.assertEqual(response.status_code, 200, response.text)
        payment = response.json()
        stored_payment = copy.deepcopy(self.db.data["debt_payments"][0])
        self.db.data["transactions"][0].update(_history_keys={"fixture": "unchanged"}, _history_debug="hidden")
        response = await self.request("PUT", "/transactions/" + payment["transaction_id"], json={"name": "Edited", "amount": 80, "type": "debt_payment", "account_id": "a"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("_history", response.text)
        self.assertEqual(self.db.data["transactions"][0]["_history_keys"], {"fixture": "unchanged"})
        self.assertEqual(self.balance(), 920)
        self.assertEqual(self.db.data["debt_payments"][0]["request_fingerprint"], stored_payment["request_fingerprint"])
        before = copy.deepcopy(self.db.data)
        retry = await self.pay(key="original")
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(self.db.data, before)


class PublicSharedRoutes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Entire fixture is synthetic memory. Its mocked settings do not activate R4.
        self.case = dispatch.SharedDispatchTests("test_unknown_commit_recovers_same_intention_and_generation")
        await self.case.asyncSetUp()

    async def test_r4_recovery_reconciliation_and_reads_sanitized(self):
        case = self.case
        payment = await case.pay_ok("bill", "original", 60)
        case.db.data["transactions"][0]["_history_keys"] = keys.derive_history_keys(case.db.data["transactions"][0], 1)
        for name in ("bill_payments", "recurring_payment_records"):
            case.db.data[name][0]["_history_debug"] = {"synthetic": True}
        before = await case.snapshot()
        retry = await case.pay_ok("bill", "original", 60)
        # Existing replay omits the optional next_bill_id=None of first creation.
        # Compare financial/public fields without changing that legacy contract.
        self.assertEqual(retry, {k: v for k, v in payment.items() if k != "next_bill_id"})
        self.assertIsNone(payment["next_bill_id"])
        self.assertNotIn("_history", repr(retry))
        response = await case.reconcile("bill", "original", 60)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("_history", response.text)
        for path in ("/bills", "/bills/bill", "/recurring-payments", "/recurring-payments/rp", "/calendar/events?start=2026-10-01&end=2026-10-31"):
            response = await case.ctx.request("GET", path)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn("_history", response.text)
        self.assertEqual(await case.snapshot(), before)

    async def test_restorable_r4_link_candidates_no_exposure_or_write(self):
        case = self.case
        payment = await case.pay_ok("bill", "original", 60)
        case.db.data["transactions"][0]["_history_keys"] = keys.derive_history_keys(case.db.data["transactions"][0], 1)
        await case.remove_ok("recurring", payment["recurring_record_id"])
        before = await case.snapshot()
        response = await case.ctx.request("GET", "/recurring-payments/rp/link-candidates?due_date=2026-10-20")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([r["id"] for r in response.json()], [payment["transaction_id"]])
        self.assertNotIn("_history", response.text)
        self.assertEqual(await case.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
