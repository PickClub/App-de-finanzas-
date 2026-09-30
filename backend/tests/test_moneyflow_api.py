"""MoneyFlow backend API tests - covers user, seed, CRUD (accounts/categories/transactions/budgets/goals/debts), debt-payments flow, and summary."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://recursing-brahmagupta-10.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- Root & User ----------
class TestBasic:
    def test_root(self, s):
        r = s.get(f"{API}/")
        assert r.status_code == 200
        assert "MoneyFlow" in r.json().get("message", "")

    def test_get_user_default(self, s):
        r = s.get(f"{API}/user")
        assert r.status_code == 200
        u = r.json()
        assert u["id"] == "default-user"
        assert "name" in u and "currency" in u

    def test_update_user(self, s):
        r = s.put(f"{API}/user", json={"name": "TEST_MoneyFlow", "currency": "USD"})
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_MoneyFlow"
        # revert
        s.put(f"{API}/user", json={"name": "Usuario"})


# ---------- Seed ----------
class TestSeed:
    def test_seed_populates(self, s):
        r = s.post(f"{API}/seed")
        assert r.status_code == 200
        assert r.json().get("seeded") is True

    def test_seed_data_exists(self, s):
        accs = s.get(f"{API}/accounts").json()
        cats = s.get(f"{API}/categories").json()
        debts = s.get(f"{API}/debts").json()
        assert len(accs) >= 3
        assert len(cats) >= 10
        assert len(debts) >= 3


# ---------- Accounts CRUD ----------
class TestAccounts:
    created_id = None

    def test_create_account(self, s):
        r = s.post(f"{API}/accounts", json={"name": "TEST_Account", "type": "cash", "initial_balance": 100.0})
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "TEST_Account"
        assert data["current_balance"] == 100.0
        TestAccounts.created_id = data["id"]

    def test_get_accounts_contains(self, s):
        r = s.get(f"{API}/accounts")
        assert r.status_code == 200
        ids = [a["id"] for a in r.json()]
        assert TestAccounts.created_id in ids

    def test_update_account(self, s):
        r = s.put(f"{API}/accounts/{TestAccounts.created_id}", json={"name": "TEST_Account2", "type": "cash", "initial_balance": 200.0})
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_Account2"

    def test_delete_account(self, s):
        r = s.delete(f"{API}/accounts/{TestAccounts.created_id}")
        assert r.status_code == 200
        ids = [a["id"] for a in s.get(f"{API}/accounts").json()]
        assert TestAccounts.created_id not in ids


# ---------- Categories CRUD ----------
class TestCategories:
    cid = None

    def test_create(self, s):
        r = s.post(f"{API}/categories", json={"name": "TEST_Cat", "type": "expense"})
        assert r.status_code == 200
        TestCategories.cid = r.json()["id"]

    def test_update(self, s):
        r = s.put(f"{API}/categories/{TestCategories.cid}", json={"name": "TEST_Cat2", "type": "expense"})
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_Cat2"

    def test_delete(self, s):
        r = s.delete(f"{API}/categories/{TestCategories.cid}")
        assert r.status_code == 200


# ---------- Transactions + Account Balance ----------
class TestTransactions:
    acc_id = None
    tx_id = None

    def test_setup_account(self, s):
        r = s.post(f"{API}/accounts", json={"name": "TEST_TxAcct", "type": "cash", "initial_balance": 1000.0})
        TestTransactions.acc_id = r.json()["id"]

    def test_create_expense_updates_balance(self, s):
        r = s.post(f"{API}/transactions", json={"name": "TEST_Expense", "amount": 50.0, "type": "expense", "account_id": TestTransactions.acc_id})
        assert r.status_code == 200
        TestTransactions.tx_id = r.json()["id"]
        acc = [a for a in s.get(f"{API}/accounts").json() if a["id"] == TestTransactions.acc_id][0]
        assert acc["current_balance"] == 950.0

    def test_create_income_updates_balance(self, s):
        r = s.post(f"{API}/transactions", json={"name": "TEST_Income", "amount": 200.0, "type": "income", "account_id": TestTransactions.acc_id})
        assert r.status_code == 200
        acc = [a for a in s.get(f"{API}/accounts").json() if a["id"] == TestTransactions.acc_id][0]
        assert acc["current_balance"] == 1150.0

    def test_list_transactions(self, s):
        r = s.get(f"{API}/transactions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_delete_transaction_restores(self, s):
        r = s.delete(f"{API}/transactions/{TestTransactions.tx_id}")
        assert r.status_code == 200
        acc = [a for a in s.get(f"{API}/accounts").json() if a["id"] == TestTransactions.acc_id][0]
        assert acc["current_balance"] == 1200.0

    def test_cleanup(self, s):
        s.delete(f"{API}/accounts/{TestTransactions.acc_id}")


# ---------- Budgets ----------
class TestBudgets:
    bid = None

    def test_create(self, s):
        r = s.post(f"{API}/budgets", json={"name": "TEST_Budget", "amount_limit": 500.0, "period": "monthly"})
        assert r.status_code == 200
        TestBudgets.bid = r.json()["id"]

    def test_update(self, s):
        r = s.put(f"{API}/budgets/{TestBudgets.bid}", json={"name": "TEST_Budget2", "amount_limit": 600.0, "period": "monthly"})
        assert r.status_code == 200
        assert r.json()["amount_limit"] == 600.0

    def test_delete(self, s):
        assert s.delete(f"{API}/budgets/{TestBudgets.bid}").status_code == 200


# ---------- Goals ----------
class TestGoals:
    gid = None

    def test_create(self, s):
        r = s.post(f"{API}/goals", json={"name": "TEST_Goal", "target_amount": 1000.0})
        assert r.status_code == 200
        TestGoals.gid = r.json()["id"]

    def test_delete(self, s):
        assert s.delete(f"{API}/goals/{TestGoals.gid}").status_code == 200


# ---------- Debts + Payments flow (critical) ----------
class TestDebtsAndPayments:
    acc_id = None
    debt_id = None

    def test_setup(self, s):
        r = s.post(f"{API}/accounts", json={"name": "TEST_DebtAcct", "type": "checking", "initial_balance": 5000.0})
        TestDebtsAndPayments.acc_id = r.json()["id"]
        r = s.post(f"{API}/debts", json={"name": "TEST_Debt", "direction": "i_owe", "person": "Bank", "original_amount": 1000.0, "minimum_payment": 100.0})
        assert r.status_code == 200
        d = r.json()
        assert d["remaining_amount"] == 1000.0
        assert d["status"] == "active"
        TestDebtsAndPayments.debt_id = d["id"]

    def test_get_debt(self, s):
        r = s.get(f"{API}/debts/{TestDebtsAndPayments.debt_id}")
        assert r.status_code == 200

    def test_partial_payment(self, s):
        r = s.post(f"{API}/debt-payments", json={"debt_id": TestDebtsAndPayments.debt_id, "amount": 400.0, "account_id": TestDebtsAndPayments.acc_id})
        assert r.status_code == 200
        # Verify debt recomputed
        d = s.get(f"{API}/debts/{TestDebtsAndPayments.debt_id}").json()
        assert d["total_paid"] == 400.0
        assert d["remaining_amount"] == 600.0
        assert d["status"] == "active"
        # Verify account balance decreased
        acc = [a for a in s.get(f"{API}/accounts").json() if a["id"] == TestDebtsAndPayments.acc_id][0]
        assert acc["current_balance"] == 4600.0
        # Verify linked transaction was created
        txs = s.get(f"{API}/transactions").json()
        linked = [t for t in txs if t.get("debt_id") == TestDebtsAndPayments.debt_id]
        assert len(linked) >= 1
        assert linked[0]["type"] == "debt_payment"

    def test_full_payment_marks_paid(self, s):
        r = s.post(f"{API}/debt-payments", json={"debt_id": TestDebtsAndPayments.debt_id, "amount": 600.0, "account_id": TestDebtsAndPayments.acc_id})
        assert r.status_code == 200
        d = s.get(f"{API}/debts/{TestDebtsAndPayments.debt_id}").json()
        assert d["remaining_amount"] == 0.0
        assert d["status"] == "paid"
        assert d["total_paid"] == 1000.0

    def test_they_owe_payment_creates_income(self, s):
        r = s.post(f"{API}/debts", json={"name": "TEST_TheyOwe", "direction": "they_owe", "person": "Friend", "original_amount": 500.0})
        did = r.json()["id"]
        r = s.post(f"{API}/debt-payments", json={"debt_id": did, "amount": 100.0, "account_id": TestDebtsAndPayments.acc_id})
        assert r.status_code == 200
        txs = s.get(f"{API}/transactions").json()
        linked = [t for t in txs if t.get("debt_id") == did]
        assert linked and linked[0]["type"] == "income"
        s.delete(f"{API}/debts/{did}")

    def test_cleanup(self, s):
        s.delete(f"{API}/debts/{TestDebtsAndPayments.debt_id}")
        s.delete(f"{API}/accounts/{TestDebtsAndPayments.acc_id}")


# ---------- Summary ----------
class TestSummary:
    def test_summary_shape(self, s):
        # Re-seed to ensure known state
        s.post(f"{API}/seed")
        r = s.get(f"{API}/summary")
        assert r.status_code == 200
        d = r.json()
        for k in ("total_balance", "month_income", "month_expense", "debts", "accounts_count"):
            assert k in d
        for k in ("i_owe", "they_owe", "paid_this_month", "next_payment"):
            assert k in d["debts"]
        assert d["debts"]["i_owe"] > 0
