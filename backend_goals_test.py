#!/usr/bin/env python3
"""
Comprehensive test suite for Saving Goals API
Tests all requirements from the review request
"""
import requests
import json
from datetime import datetime, timedelta, date
from decimal import Decimal

BASE = "http://127.0.0.1:8013/api"
HEADERS = {"Content-Type": "application/json"}

# Test results tracking
results = {
    "passed": [],
    "failed": [],
    "total": 0
}

def test(name, condition, details=""):
    """Track test results"""
    results["total"] += 1
    if condition:
        results["passed"].append(f"✅ {name}")
        print(f"✅ {name}")
    else:
        results["failed"].append(f"❌ {name}: {details}")
        print(f"❌ {name}: {details}")
    return condition

def get_account_balance(account_id):
    """Get current balance of an account"""
    r = requests.get(f"{BASE}/accounts", headers=HEADERS)
    accounts = r.json()
    acc = next((a for a in accounts if a["id"] == account_id), None)
    return acc["current_balance"] if acc else 0

def check_no_leakage(data, test_name):
    """Check for _id or request_fingerprint leakage"""
    if isinstance(data, dict):
        if "_id" in data:
            test(f"{test_name} - No _id leakage", False, f"Found _id in response")
            return False
        if "request_fingerprint" in data:
            test(f"{test_name} - No request_fingerprint leakage", False, f"Found request_fingerprint in response")
            return False
        for v in data.values():
            if isinstance(v, (dict, list)):
                if not check_no_leakage(v, test_name):
                    return False
    elif isinstance(data, list):
        for item in data:
            if not check_no_leakage(item, test_name):
                return False
    return True

print("=" * 80)
print("SAVING GOALS API COMPREHENSIVE TEST SUITE")
print("=" * 80)
print()

# ============================================================================
# TEST 1: VALIDATION ERRORS (422)
# ============================================================================
print("\n[TEST 1] VALIDATION ERRORS (422)")
print("-" * 80)

# 1.1 Empty name
r = requests.post(f"{BASE}/goals", json={"name": "", "target_amount": 1000}, headers=HEADERS)
test("1.1 Empty name → 422", r.status_code == 422, f"Got {r.status_code}")

# 1.2 Target amount <= 0
r = requests.post(f"{BASE}/goals", json={"name": "Test Goal", "target_amount": 0}, headers=HEADERS)
test("1.2 Target amount = 0 → 422", r.status_code == 422, f"Got {r.status_code}")

r = requests.post(f"{BASE}/goals", json={"name": "Test Goal", "target_amount": -100}, headers=HEADERS)
test("1.3 Target amount < 0 → 422", r.status_code == 422, f"Got {r.status_code}")

# 1.4 Invalid target_date
r = requests.post(f"{BASE}/goals", json={"name": "Test Goal", "target_amount": 1000, "target_date": "2027-13-45"}, headers=HEADERS)
test("1.4 Invalid target_date → 422", r.status_code == 422, f"Got {r.status_code}")

# 1.5 Negative initial_amount
r = requests.post(f"{BASE}/goals", json={"name": "Test Goal", "target_amount": 1000, "initial_amount": -50}, headers=HEADERS)
test("1.5 Negative initial_amount → 422", r.status_code == 422, f"Got {r.status_code}")

# 1.6 Unknown account_id
r = requests.post(f"{BASE}/goals", json={"name": "Test Goal", "target_amount": 1000, "account_id": "nonexistent-account-id"}, headers=HEADERS)
test("1.6 Unknown account_id → 422", r.status_code == 422, f"Got {r.status_code}")

# ============================================================================
# TEST 2: DUPLICATE NAME CONFLICT (409)
# ============================================================================
print("\n[TEST 2] DUPLICATE NAME CONFLICT (409)")
print("-" * 80)

# Create first goal
r = requests.post(f"{BASE}/goals", json={"name": "Vacation Fund", "target_amount": 5000}, headers=HEADERS)
test("2.1 Create first goal", r.status_code == 200, f"Got {r.status_code}")
goal1 = r.json()

# Try to create duplicate (exact case)
r = requests.post(f"{BASE}/goals", json={"name": "Vacation Fund", "target_amount": 3000}, headers=HEADERS)
test("2.2 Duplicate name (exact case) → 409", r.status_code == 409, f"Got {r.status_code}")

# Try to create duplicate (different case)
r = requests.post(f"{BASE}/goals", json={"name": "vacation fund", "target_amount": 3000}, headers=HEADERS)
test("2.3 Duplicate name (case-insensitive) → 409", r.status_code == 409, f"Got {r.status_code}")

# ============================================================================
# TEST 3: IDEMPOTENCY KEY
# ============================================================================
print("\n[TEST 3] IDEMPOTENCY KEY")
print("-" * 80)

# 3.1 Same key, same body → returns same goal
headers_idem = {**HEADERS, "Idempotency-Key": "test-idem-key-1"}
r1 = requests.post(f"{BASE}/goals", json={"name": "Emergency Fund", "target_amount": 10000}, headers=headers_idem)
test("3.1 First request with idempotency key", r1.status_code == 200, f"Got {r1.status_code}")
goal_idem1 = r1.json()

r2 = requests.post(f"{BASE}/goals", json={"name": "Emergency Fund", "target_amount": 10000}, headers=headers_idem)
test("3.2 Second request with same key and body", r2.status_code == 200, f"Got {r2.status_code}")
goal_idem2 = r2.json()

test("3.3 Same goal ID returned", goal_idem1["id"] == goal_idem2["id"], f"{goal_idem1['id']} vs {goal_idem2['id']}")

# 3.2 Same key, different body → 409
headers_idem2 = {**HEADERS, "Idempotency-Key": "test-idem-key-2"}
r1 = requests.post(f"{BASE}/goals", json={"name": "Car Fund", "target_amount": 20000}, headers=headers_idem2)
test("3.4 First request with idempotency key 2", r1.status_code == 200, f"Got {r1.status_code}")

r2 = requests.post(f"{BASE}/goals", json={"name": "Car Fund", "target_amount": 25000}, headers=headers_idem2)
test("3.5 Same key, different body → 409", r2.status_code == 409, f"Got {r2.status_code}")

# 3.3 Check no leakage
check_no_leakage(goal_idem1, "3.6 Idempotency response")

# ============================================================================
# TEST 4: CREATE GOALS WITH INITIAL AMOUNTS & OVERVIEW
# ============================================================================
print("\n[TEST 4] CREATE GOALS WITH INITIAL AMOUNTS & OVERVIEW")
print("-" * 80)

# Create accounts for later tests
r = requests.post(f"{BASE}/accounts", json={"name": "Source Account", "type": "checking", "initial_balance": 1000}, headers=HEADERS)
test("4.1 Create source account", r.status_code == 200, f"Got {r.status_code}")
source_account = r.json()

r = requests.post(f"{BASE}/accounts", json={"name": "Savings Account", "type": "savings", "initial_balance": 0}, headers=HEADERS)
test("4.2 Create savings account", r.status_code == 200, f"Got {r.status_code}")
savings_account = r.json()

# Create goals with initial amounts
r = requests.post(f"{BASE}/goals", json={
    "name": "House Down Payment",
    "target_amount": 50000,
    "initial_amount": 5000,
    "account_id": savings_account["id"]
}, headers=HEADERS)
test("4.3 Create goal with initial amount", r.status_code == 200, f"Got {r.status_code}")
house_goal = r.json()
test("4.4 Initial amount set correctly", house_goal["current_amount"] == 5000, f"Got {house_goal['current_amount']}")

r = requests.post(f"{BASE}/goals", json={
    "name": "Wedding Fund",
    "target_amount": 30000,
    "initial_amount": 10000
}, headers=HEADERS)
test("4.5 Create second goal with initial amount", r.status_code == 200, f"Got {r.status_code}")
wedding_goal = r.json()

# Get overview
r = requests.get(f"{BASE}/goals/overview", headers=HEADERS)
test("4.6 Get goals overview", r.status_code == 200, f"Got {r.status_code}")
overview = r.json()

# Check totals
expected_saved = 5000 + 10000  # house + wedding initial amounts
expected_target = 50000 + 30000 + 5000 + 10000 + 20000  # all goals created so far
test("4.7 Overview has totals", "totals" in overview, "Missing totals")
test("4.8 Overview has active_count", "active_count" in overview, "Missing active_count")
test("4.9 Overview has completed_count", "completed_count" in overview, "Missing completed_count")
test("4.10 Overview has goals list", "goals" in overview, "Missing goals")

# Check saved calculation
totals = overview["totals"]
test("4.11 Saved amount calculated", totals["saved"] >= 15000, f"Got {totals['saved']}")

# Check remaining calculation (sum of per-goal max(0, target-saved))
test("4.12 Remaining is non-negative", totals["remaining"] >= 0, f"Got {totals['remaining']}")

# Check pct calculation (saved/target*100 or null)
if totals["target"] > 0:
    expected_pct = round(totals["saved"] / totals["target"] * 100, 1)
    test("4.13 Percentage calculated correctly", abs(totals["pct"] - expected_pct) < 0.2, f"Expected ~{expected_pct}, got {totals['pct']}")
else:
    test("4.13 Percentage is null when no target", totals["pct"] is None, f"Got {totals['pct']}")

# ============================================================================
# TEST 5: CONTRIBUTIONS - TRACKING ONLY (no real_movement)
# ============================================================================
print("\n[TEST 5] CONTRIBUTIONS - TRACKING ONLY (no real_movement)")
print("-" * 80)

# Get baseline summary
r = requests.get(f"{BASE}/summary", headers=HEADERS)
baseline_summary = r.json()
baseline_total_balance = baseline_summary["total_balance"]

# Get baseline account balances
baseline_source_balance = get_account_balance(source_account["id"])
baseline_savings_balance = get_account_balance(savings_account["id"])

# 5.1 Deposit tracking (no real_movement)
r = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 1000,
    "date": datetime.now().isoformat(),
    "notes": "Monthly savings"
}, headers=HEADERS)
test("5.1 Create tracking deposit", r.status_code == 200, f"Got {r.status_code}")
contrib1 = r.json()

test("5.2 Contribution response has contribution", "contribution" in contrib1, "Missing contribution")
test("5.3 Contribution response has goal", "goal" in contrib1, "Missing goal")

# Check goal saved amount increased
updated_goal = contrib1["goal"]
test("5.4 Saved amount increased", updated_goal["current_amount"] == 6000, f"Expected 6000, got {updated_goal['current_amount']}")

# Check NO transaction created
r = requests.get(f"{BASE}/transactions", headers=HEADERS)
transactions = r.json()
tracking_tx = [tx for tx in transactions if tx.get("goal_id") == house_goal["id"]]
test("5.5 No transaction created for tracking deposit", len(tracking_tx) == 0, f"Found {len(tracking_tx)} transactions")

# Check account balances unchanged
source_balance_after = get_account_balance(source_account["id"])
test("5.6 Source account balance unchanged", source_balance_after == baseline_source_balance, 
     f"Expected {baseline_source_balance}, got {source_balance_after}")

savings_balance_after = get_account_balance(savings_account["id"])
test("5.7 Savings account balance unchanged", savings_balance_after == baseline_savings_balance,
     f"Expected {baseline_savings_balance}, got {savings_balance_after}")

# Check summary unchanged
r = requests.get(f"{BASE}/summary", headers=HEADERS)
current_summary = r.json()
test("5.8 Total balance unchanged", current_summary["total_balance"] == baseline_total_balance,
     f"Expected {baseline_total_balance}, got {current_summary['total_balance']}")
test("5.9 Month income unchanged", current_summary["month_income"] == baseline_summary["month_income"],
     f"Expected {baseline_summary['month_income']}, got {current_summary['month_income']}")
test("5.10 Month expense unchanged", current_summary["month_expense"] == baseline_summary["month_expense"],
     f"Expected {baseline_summary['month_expense']}, got {current_summary['month_expense']}")

# 5.2 Withdrawal tracking
r = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "withdrawal",
    "amount": 500,
    "date": datetime.now().isoformat(),
    "notes": "Emergency withdrawal"
}, headers=HEADERS)
test("5.11 Create tracking withdrawal", r.status_code == 200, f"Got {r.status_code}")
contrib2 = r.json()

# Check saved amount decreased
updated_goal = contrib2["goal"]
test("5.12 Saved amount decreased", updated_goal["current_amount"] == 5500, f"Expected 5500, got {updated_goal['current_amount']}")

# 5.3 Withdrawal > saved → 422
r = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "withdrawal",
    "amount": 10000,
    "date": datetime.now().isoformat()
}, headers=HEADERS)
test("5.13 Withdrawal > saved → 422", r.status_code == 422, f"Got {r.status_code}")

# 5.4 Amount <= 0 → 422
r = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 0,
    "date": datetime.now().isoformat()
}, headers=HEADERS)
test("5.14 Amount = 0 → 422", r.status_code == 422, f"Got {r.status_code}")

r = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": -100,
    "date": datetime.now().isoformat()
}, headers=HEADERS)
test("5.15 Amount < 0 → 422", r.status_code == 422, f"Got {r.status_code}")

# 5.5 Idempotency-Key replay doesn't duplicate
fixed_date = datetime.now().isoformat()
headers_contrib_idem = {**HEADERS, "Idempotency-Key": "contrib-idem-1"}
r1 = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 200,
    "date": fixed_date
}, headers=headers_contrib_idem)
test("5.16 First contribution with idempotency key", r1.status_code == 200, f"Got {r1.status_code}")
saved_after_first = r1.json()["goal"]["current_amount"]

r2 = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 200,
    "date": fixed_date
}, headers=headers_contrib_idem)
test("5.17 Second contribution with same key", r2.status_code == 200, f"Got {r2.status_code}")
saved_after_second = r2.json()["goal"]["current_amount"]

test("5.18 Idempotency prevents duplicate", saved_after_first == saved_after_second,
     f"First: {saved_after_first}, Second: {saved_after_second}")

# ============================================================================
# TEST 6: REAL MOVEMENT
# ============================================================================
print("\n[TEST 6] REAL MOVEMENT")
print("-" * 80)

# Get fresh baseline
source_balance_before = get_account_balance(source_account["id"])
savings_balance_before = get_account_balance(savings_account["id"])

r = requests.get(f"{BASE}/summary", headers=HEADERS)
summary_before = r.json()
total_balance_before = summary_before["total_balance"]
month_income_before = summary_before["month_income"]
month_expense_before = summary_before["month_expense"]

# Get transaction count before
r = requests.get(f"{BASE}/transactions", headers=HEADERS)
tx_count_before = len(r.json())

# 6.1 Deposit with real_movement
r = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 200,
    "date": datetime.now().isoformat(),
    "account_id": source_account["id"],
    "real_movement": True,
    "notes": "Real transfer to savings"
}, headers=HEADERS)
test("6.1 Create deposit with real_movement", r.status_code == 200, f"Got {r.status_code}")
real_contrib = r.json()

# Check exactly ONE transfer transaction created
r = requests.get(f"{BASE}/transactions", headers=HEADERS)
transactions = r.json()
tx_count_after = len(transactions)
test("6.2 Exactly one transaction created", tx_count_after == tx_count_before + 1,
     f"Expected {tx_count_before + 1}, got {tx_count_after}")

# Find the transfer transaction
transfer_tx = [tx for tx in transactions if tx.get("goal_id") == house_goal["id"] and tx["type"] == "transfer"]
test("6.3 Transfer transaction exists", len(transfer_tx) == 1, f"Found {len(transfer_tx)} transfers")

if transfer_tx:
    tx = transfer_tx[0]
    test("6.4 Transfer from source to savings", 
         tx["account_id"] == source_account["id"] and tx["to_account_id"] == savings_account["id"],
         f"From {tx['account_id']} to {tx['to_account_id']}")
    test("6.5 Transfer amount correct", tx["amount"] == 200, f"Got {tx['amount']}")

# Check account balances updated
source_balance_after = get_account_balance(source_account["id"])
test("6.6 Source account decreased", source_balance_after == source_balance_before - 200,
     f"Expected {source_balance_before - 200}, got {source_balance_after}")

savings_balance_after = get_account_balance(savings_account["id"])
test("6.7 Savings account increased", savings_balance_after == savings_balance_before + 200,
     f"Expected {savings_balance_before + 200}, got {savings_balance_after}")

# Check total_balance unchanged (transfer between accounts)
r = requests.get(f"{BASE}/summary", headers=HEADERS)
summary_after = r.json()
test("6.8 Total balance unchanged", summary_after["total_balance"] == total_balance_before,
     f"Expected {total_balance_before}, got {summary_after['total_balance']}")

# Check income/expense unchanged (transfer doesn't affect these)
test("6.9 Month income unchanged", summary_after["month_income"] == month_income_before,
     f"Expected {month_income_before}, got {summary_after['month_income']}")
test("6.10 Month expense unchanged", summary_after["month_expense"] == month_expense_before,
     f"Expected {month_expense_before}, got {summary_after['month_expense']}")

# 6.2 Real movement without goal account → 422
r = requests.post(f"{BASE}/goals/{wedding_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 100,
    "account_id": source_account["id"],
    "real_movement": True
}, headers=HEADERS)
test("6.11 Real movement without goal account → 422", r.status_code == 422, f"Got {r.status_code}")

# 6.3 Real movement without account_id → 422
r = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 100,
    "real_movement": True
}, headers=HEADERS)
test("6.12 Real movement without account_id → 422", r.status_code == 422, f"Got {r.status_code}")

# 6.4 Real movement with same account as goal → 422
r = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 100,
    "account_id": savings_account["id"],
    "real_movement": True
}, headers=HEADERS)
test("6.13 Real movement with same account → 422", r.status_code == 422, f"Got {r.status_code}")

# 6.5 Real withdrawal (reverse direction)
source_before_withdrawal = get_account_balance(source_account["id"])
savings_before_withdrawal = get_account_balance(savings_account["id"])

r = requests.post(f"{BASE}/goals/{house_goal['id']}/contributions", json={
    "kind": "withdrawal",
    "amount": 50,
    "account_id": source_account["id"],
    "real_movement": True,
    "notes": "Emergency withdrawal"
}, headers=HEADERS)
test("6.14 Create withdrawal with real_movement", r.status_code == 200, f"Got {r.status_code}")

# Check transfer direction (savings → source)
r = requests.get(f"{BASE}/transactions", headers=HEADERS)
transactions = r.json()
withdrawal_tx = [tx for tx in transactions if tx.get("notes") == "Emergency withdrawal"]
test("6.15 Withdrawal transfer exists", len(withdrawal_tx) == 1, f"Found {len(withdrawal_tx)}")

if withdrawal_tx:
    tx = withdrawal_tx[0]
    test("6.16 Withdrawal from savings to source",
         tx["account_id"] == savings_account["id"] and tx["to_account_id"] == source_account["id"],
         f"From {tx['account_id']} to {tx['to_account_id']}")

# Check balances
source_after_withdrawal = get_account_balance(source_account["id"])
test("6.17 Source account increased", source_after_withdrawal == source_before_withdrawal + 50,
     f"Expected {source_before_withdrawal + 50}, got {source_after_withdrawal}")

savings_after_withdrawal = get_account_balance(savings_account["id"])
test("6.18 Savings account decreased", savings_after_withdrawal == savings_before_withdrawal - 50,
     f"Expected {savings_before_withdrawal - 50}, got {savings_after_withdrawal}")

# 6.6 Try to edit linked transaction → 409
if transfer_tx:
    linked_tx_id = transfer_tx[0]["id"]
    r = requests.put(f"{BASE}/transactions/{linked_tx_id}", json={
        "name": "Modified transfer",
        "amount": 300,
        "type": "transfer",
        "account_id": source_account["id"],
        "to_account_id": savings_account["id"]
    }, headers=HEADERS)
    test("6.19 PUT linked transaction → 409", r.status_code == 409, f"Got {r.status_code}")

    # 6.7 Try to delete linked transaction → 409
    r = requests.delete(f"{BASE}/transactions/{linked_tx_id}", headers=HEADERS)
    test("6.20 DELETE linked transaction → 409", r.status_code == 409, f"Got {r.status_code}")

# ============================================================================
# TEST 7: COMPLETION
# ============================================================================
print("\n[TEST 7] COMPLETION")
print("-" * 80)

# Create a goal that will be completed
r = requests.post(f"{BASE}/goals", json={
    "name": "Small Goal",
    "target_amount": 100,
    "initial_amount": 50
}, headers=HEADERS)
test("7.1 Create small goal", r.status_code == 200, f"Got {r.status_code}")
small_goal = r.json()

# Add contribution to reach target
r = requests.post(f"{BASE}/goals/{small_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 50
}, headers=HEADERS)
test("7.2 Add contribution to reach target", r.status_code == 200, f"Got {r.status_code}")
completed_goal = r.json()["goal"]

test("7.3 Goal marked as completed", completed_goal["completed"] == True, f"Got {completed_goal['completed']}")
test("7.4 completed_at is set", completed_goal["completed_at"] is not None, "completed_at is None")
test("7.5 Percentage is 100", completed_goal["pct"] == 100.0, f"Got {completed_goal['pct']}")

# Add more to exceed target
r = requests.post(f"{BASE}/goals/{small_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 32.5
}, headers=HEADERS)
test("7.6 Add contribution to exceed target", r.status_code == 200, f"Got {r.status_code}")
exceeded_goal = r.json()["goal"]

test("7.7 Percentage can exceed 100", exceeded_goal["pct"] > 100, f"Got {exceeded_goal['pct']}")
expected_pct = round(132.5 / 100 * 100, 1)
test("7.8 Percentage calculated correctly", abs(exceeded_goal["pct"] - expected_pct) < 0.2,
     f"Expected ~{expected_pct}, got {exceeded_goal['pct']}")

# Lower target to make it incomplete
r = requests.put(f"{BASE}/goals/{small_goal['id']}", json={
    "name": "Small Goal",
    "target_amount": 200
}, headers=HEADERS)
test("7.9 Lower target (make incomplete)", r.status_code == 200, f"Got {r.status_code}")
incomplete_goal = r.json()

test("7.10 Goal no longer completed", incomplete_goal["completed"] == False, f"Got {incomplete_goal['completed']}")
test("7.11 completed_at cleared", incomplete_goal["completed_at"] is None, f"Got {incomplete_goal['completed_at']}")

# Raise target back to complete it
r = requests.put(f"{BASE}/goals/{small_goal['id']}", json={
    "name": "Small Goal",
    "target_amount": 100
}, headers=HEADERS)
test("7.12 Raise target (make complete again)", r.status_code == 200, f"Got {r.status_code}")
recompleted_goal = r.json()

test("7.13 Goal completed again", recompleted_goal["completed"] == True, f"Got {recompleted_goal['completed']}")
test("7.14 completed_at set again", recompleted_goal["completed_at"] is not None, "completed_at is None")

# ============================================================================
# TEST 8: MONTHLY RECOMMENDED
# ============================================================================
print("\n[TEST 8] MONTHLY RECOMMENDED")
print("-" * 80)

# 8.1 No target_date → monthly_recommended is null
r = requests.post(f"{BASE}/goals", json={
    "name": "No Date Goal",
    "target_amount": 1000,
    "initial_amount": 100
}, headers=HEADERS)
test("8.1 Create goal without target_date", r.status_code == 200, f"Got {r.status_code}")
no_date_goal = r.json()
test("8.2 monthly_recommended is null", no_date_goal["monthly_recommended"] is None,
     f"Got {no_date_goal['monthly_recommended']}")

# 8.2 Future date → positive integer (ceil)
future_date = (date.today() + timedelta(days=90)).isoformat()
r = requests.post(f"{BASE}/goals", json={
    "name": "Future Goal",
    "target_amount": 3000,
    "initial_amount": 500,
    "target_date": future_date
}, headers=HEADERS)
test("8.3 Create goal with future date", r.status_code == 200, f"Got {r.status_code}")
future_goal = r.json()

test("8.4 monthly_recommended is positive integer", 
     isinstance(future_goal["monthly_recommended"], int) and future_goal["monthly_recommended"] > 0,
     f"Got {future_goal['monthly_recommended']}")

# Check it's ceiling (rounded up)
remaining = future_goal["remaining"]
days_left = future_goal["days_left"]
if days_left and days_left > 0:
    months = max(1, (days_left + 1) / 30.436875)
    expected_recommended = int(Decimal(str(remaining)) / Decimal(str(months)))
    if Decimal(str(remaining)) % Decimal(str(months)) > 0:
        expected_recommended += 1
    test("8.5 monthly_recommended is ceiling", 
         future_goal["monthly_recommended"] >= expected_recommended,
         f"Expected >={expected_recommended}, got {future_goal['monthly_recommended']}")

# 8.3 Past date with remaining > 0 → overdue=true, recommended null
past_date = (date.today() - timedelta(days=30)).isoformat()
r = requests.post(f"{BASE}/goals", json={
    "name": "Overdue Goal",
    "target_amount": 5000,
    "initial_amount": 1000,
    "target_date": past_date
}, headers=HEADERS)
test("8.6 Create goal with past date", r.status_code == 200, f"Got {r.status_code}")
overdue_goal = r.json()

test("8.7 overdue is true", overdue_goal["overdue"] == True, f"Got {overdue_goal['overdue']}")
test("8.8 monthly_recommended is null for overdue", overdue_goal["monthly_recommended"] is None,
     f"Got {overdue_goal['monthly_recommended']}")

# ============================================================================
# TEST 9: PAGINATION
# ============================================================================
print("\n[TEST 9] PAGINATION")
print("-" * 80)

# Create a goal with multiple contributions
r = requests.post(f"{BASE}/goals", json={
    "name": "Pagination Test Goal",
    "target_amount": 10000
}, headers=HEADERS)
test("9.1 Create goal for pagination test", r.status_code == 200, f"Got {r.status_code}")
page_goal = r.json()

# Add 5 contributions
for i in range(5):
    r = requests.post(f"{BASE}/goals/{page_goal['id']}/contributions", json={
        "kind": "deposit",
        "amount": 100 * (i + 1),
        "date": (datetime.now() - timedelta(days=i)).isoformat(),
        "notes": f"Contribution {i+1}"
    }, headers=HEADERS)
    test(f"9.{i+2} Add contribution {i+1}", r.status_code == 200, f"Got {r.status_code}")

# Test pagination with limit=2, offset=0
r = requests.get(f"{BASE}/goals/{page_goal['id']}/contributions?limit=2&offset=0", headers=HEADERS)
test("9.7 Get contributions page 1", r.status_code == 200, f"Got {r.status_code}")
page1 = r.json()

test("9.8 Page has items", "items" in page1, "Missing items")
test("9.9 Page has total", "total" in page1, "Missing total")
test("9.10 Page has offset", "offset" in page1, "Missing offset")
test("9.11 Page has limit", "limit" in page1, "Missing limit")
test("9.12 Page has has_more", "has_more" in page1, "Missing has_more")

test("9.13 Limit respected", len(page1["items"]) == 2, f"Expected 2, got {len(page1['items'])}")
test("9.14 Total is 5", page1["total"] == 5, f"Got {page1['total']}")
test("9.15 has_more is true", page1["has_more"] == True, f"Got {page1['has_more']}")

# Check sorting (date desc)
if len(page1["items"]) >= 2:
    date1 = datetime.fromisoformat(page1["items"][0]["date"].replace("Z", "+00:00"))
    date2 = datetime.fromisoformat(page1["items"][1]["date"].replace("Z", "+00:00"))
    test("9.16 Sorted by date desc", date1 >= date2, f"{date1} vs {date2}")

# Test pagination with limit=2, offset=2
r = requests.get(f"{BASE}/goals/{page_goal['id']}/contributions?limit=2&offset=2", headers=HEADERS)
test("9.17 Get contributions page 2", r.status_code == 200, f"Got {r.status_code}")
page2 = r.json()

test("9.18 Page 2 has 2 items", len(page2["items"]) == 2, f"Got {len(page2['items'])}")
test("9.19 Page 2 has_more is true", page2["has_more"] == True, f"Got {page2['has_more']}")

# Test last page
r = requests.get(f"{BASE}/goals/{page_goal['id']}/contributions?limit=2&offset=4", headers=HEADERS)
test("9.20 Get contributions last page", r.status_code == 200, f"Got {r.status_code}")
page3 = r.json()

test("9.21 Last page has 1 item", len(page3["items"]) == 1, f"Got {len(page3['items'])}")
test("9.22 Last page has_more is false", page3["has_more"] == False, f"Got {page3['has_more']}")

# Test GET /goals/{id} includes contributions page
r = requests.get(f"{BASE}/goals/{page_goal['id']}", headers=HEADERS)
test("9.23 Get goal detail", r.status_code == 200, f"Got {r.status_code}")
goal_detail = r.json()

test("9.24 Detail includes contributions", "contributions" in goal_detail, "Missing contributions")
test("9.25 Detail includes account", "account" in goal_detail, "Missing account")

# ============================================================================
# TEST 10: UPDATE & DELETE
# ============================================================================
print("\n[TEST 10] UPDATE & DELETE")
print("-" * 80)

# 10.1 PUT nonexistent goal → 404
r = requests.put(f"{BASE}/goals/nonexistent-goal-id", json={
    "name": "Updated Goal",
    "target_amount": 5000
}, headers=HEADERS)
test("10.1 PUT nonexistent goal → 404", r.status_code == 404, f"Got {r.status_code}")

# 10.2 Edit without initial_amount keeps initial
r = requests.post(f"{BASE}/goals", json={
    "name": "Edit Test Goal",
    "target_amount": 2000,
    "initial_amount": 300
}, headers=HEADERS)
test("10.2 Create goal for edit test", r.status_code == 200, f"Got {r.status_code}")
edit_goal = r.json()
original_initial = edit_goal["initial_amount"]

r = requests.put(f"{BASE}/goals/{edit_goal['id']}", json={
    "name": "Updated Edit Test Goal",
    "target_amount": 2500
}, headers=HEADERS)
test("10.3 Update goal without initial_amount", r.status_code == 200, f"Got {r.status_code}")
updated_goal = r.json()

test("10.4 initial_amount preserved", updated_goal["initial_amount"] == original_initial,
     f"Expected {original_initial}, got {updated_goal['initial_amount']}")

# 10.3 DELETE goal
# First add some contributions
r = requests.post(f"{BASE}/goals/{edit_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 100
}, headers=HEADERS)
test("10.5 Add contribution before delete", r.status_code == 200, f"Got {r.status_code}")

# Add a real movement contribution to create a linked transfer
r = requests.post(f"{BASE}/goals", json={
    "name": "Delete Test Goal",
    "target_amount": 1000,
    "account_id": savings_account["id"]
}, headers=HEADERS)
test("10.6 Create goal with account for delete test", r.status_code == 200, f"Got {r.status_code}")
delete_goal = r.json()

r = requests.post(f"{BASE}/goals/{delete_goal['id']}/contributions", json={
    "kind": "deposit",
    "amount": 100,
    "account_id": source_account["id"],
    "real_movement": True
}, headers=HEADERS)
test("10.7 Add real movement contribution", r.status_code == 200, f"Got {r.status_code}")

# Get the linked transfer
r = requests.get(f"{BASE}/transactions", headers=HEADERS)
transactions = r.json()
linked_transfer = [tx for tx in transactions if tx.get("goal_id") == delete_goal["id"]]
test("10.8 Linked transfer exists", len(linked_transfer) > 0, f"Found {len(linked_transfer)}")

if linked_transfer:
    linked_tx_id = linked_transfer[0]["id"]
    
    # Get account balances before delete
    source_before_delete = get_account_balance(source_account["id"])
    savings_before_delete = get_account_balance(savings_account["id"])
    
    # Delete the goal
    r = requests.delete(f"{BASE}/goals/{delete_goal['id']}", headers=HEADERS)
    test("10.9 Delete goal", r.status_code == 200, f"Got {r.status_code}")
    
    # Check goal is removed
    r = requests.get(f"{BASE}/goals", headers=HEADERS)
    goals = r.json()
    deleted_goal_exists = any(g["id"] == delete_goal["id"] for g in goals)
    test("10.10 Goal removed from list", not deleted_goal_exists, "Goal still exists")
    
    # Check contributions are removed
    r = requests.get(f"{BASE}/goals/{delete_goal['id']}/contributions", headers=HEADERS)
    test("10.11 Contributions endpoint returns 404", r.status_code == 404, f"Got {r.status_code}")
    
    # Check linked transfer still exists but unlinked
    r = requests.get(f"{BASE}/transactions", headers=HEADERS)
    transactions = r.json()
    unlinked_tx = [tx for tx in transactions if tx["id"] == linked_tx_id]
    test("10.12 Linked transfer still exists", len(unlinked_tx) == 1, f"Found {len(unlinked_tx)}")
    
    if unlinked_tx:
        tx = unlinked_tx[0]
        test("10.13 Transfer unlinked (no goal_id)", "goal_id" not in tx or tx["goal_id"] is None,
             f"goal_id = {tx.get('goal_id')}")
    
    # Check balances unchanged
    source_after_delete = get_account_balance(source_account["id"])
    test("10.14 Source balance unchanged after delete", source_after_delete == source_before_delete,
         f"Expected {source_before_delete}, got {source_after_delete}")
    
    savings_after_delete = get_account_balance(savings_account["id"])
    test("10.15 Savings balance unchanged after delete", savings_after_delete == savings_before_delete,
         f"Expected {savings_before_delete}, got {savings_after_delete}")
    
    # Now the formerly linked transfer can be deleted normally
    r = requests.delete(f"{BASE}/transactions/{linked_tx_id}", headers=HEADERS)
    test("10.16 Formerly linked transfer can be deleted", r.status_code == 200, f"Got {r.status_code}")

# ============================================================================
# TEST 11: NO LEAKAGE IN RESPONSES
# ============================================================================
print("\n[TEST 11] NO LEAKAGE IN RESPONSES")
print("-" * 80)

# Check various endpoints for leakage
r = requests.get(f"{BASE}/goals", headers=HEADERS)
test("11.1 GET /goals - no leakage", check_no_leakage(r.json(), "GET /goals"), "")

r = requests.get(f"{BASE}/goals/overview", headers=HEADERS)
test("11.2 GET /goals/overview - no leakage", check_no_leakage(r.json(), "GET /goals/overview"), "")

if len(r.json()["goals"]) > 0:
    goal_id = r.json()["goals"][0]["id"]
    r = requests.get(f"{BASE}/goals/{goal_id}", headers=HEADERS)
    test("11.3 GET /goals/{id} - no leakage", check_no_leakage(r.json(), "GET /goals/{id}"), "")
    
    r = requests.get(f"{BASE}/goals/{goal_id}/contributions", headers=HEADERS)
    test("11.4 GET /goals/{id}/contributions - no leakage", check_no_leakage(r.json(), "GET /goals/{id}/contributions"), "")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print(f"Total tests: {results['total']}")
print(f"Passed: {len(results['passed'])} ({len(results['passed'])/results['total']*100:.1f}%)")
print(f"Failed: {len(results['failed'])} ({len(results['failed'])/results['total']*100:.1f}%)")
print()

if results['failed']:
    print("FAILED TESTS:")
    print("-" * 80)
    for failure in results['failed']:
        print(failure)
    print()

print("=" * 80)
print(f"RESULT: {'✅ ALL TESTS PASSED' if not results['failed'] else '❌ SOME TESTS FAILED'}")
print("=" * 80)
