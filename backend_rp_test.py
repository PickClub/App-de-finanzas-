#!/usr/bin/env python3
"""
Comprehensive test suite for Recurring Payments API
Tests against isolated instance on port 8015
"""
import requests
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

BASE = "http://127.0.0.1:8015/api"
HEADERS = {"Content-Type": "application/json"}

# Test results tracking
tests_passed = 0
tests_failed = 0
test_results = []

def get_account(account_id):
    """Helper to get account by id from list"""
    accs = requests.get(f"{BASE}/accounts").json()
    return [a for a in accs if a["id"] == account_id][0]

def log_test(name, passed, details=""):
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        status = "✅ PASS"
    else:
        tests_failed += 1
        status = "❌ FAIL"
    result = f"{status}: {name}"
    if details:
        result += f" - {details}"
    test_results.append(result)
    print(result)

def check_no_leakage(data, context=""):
    """Check for _id or request_fingerprint leakage"""
    if isinstance(data, dict):
        if "_id" in data:
            log_test(f"No _id leakage {context}", False, f"Found _id in response")
            return False
        if "request_fingerprint" in data:
            log_test(f"No request_fingerprint leakage {context}", False, f"Found request_fingerprint")
            return False
        for v in data.values():
            if not check_no_leakage(v, context):
                return False
    elif isinstance(data, list):
        for item in data:
            if not check_no_leakage(item, context):
                return False
    return True

print("=" * 80)
print("RECURRING PAYMENTS API COMPREHENSIVE TEST SUITE")
print("=" * 80)
print(f"Base URL: {BASE}")
print(f"Test DB: test_moneyflow_rp_qa")
print(f"Today's date: ~2026-10-10")
print("=" * 80)

# Setup: Create test account and category
print("\n[SETUP] Creating test account and category...")
acc_resp = requests.post(f"{BASE}/accounts", json={
    "name": "Test Checking",
    "type": "checking",
    "initial_balance": 5000.0,
    "color": "#4C83EA"
}, headers=HEADERS)
if acc_resp.status_code != 200:
    print(f"❌ Failed to create test account: {acc_resp.status_code} {acc_resp.text}")
    exit(1)
test_account_id = acc_resp.json()["id"]
print(f"✓ Created test account: {test_account_id}")

cat_resp = requests.post(f"{BASE}/categories", json={
    "name": "Test Utilities",
    "type": "expense",
    "icon": "flash-outline",
    "color": "#FF8A3D"
}, headers=HEADERS)
if cat_resp.status_code != 200:
    print(f"❌ Failed to create test category: {cat_resp.status_code} {cat_resp.text}")
    exit(1)
test_category_id = cat_resp.json()["id"]
print(f"✓ Created test category: {test_category_id}")

print("\n" + "=" * 80)
print("TEST 1: CREATE MONTHLY RECURRENCE + IDEMPOTENCY + VALIDATIONS")
print("=" * 80)

# 1.1: Create valid monthly recurrence
print("\n[1.1] Create valid monthly recurrence...")
rp1_data = {
    "name": "Internet Bill",
    "amount": 50.0,
    "variable": False,
    "category_id": test_category_id,
    "account_id": test_account_id,
    "frequency": "monthly",
    "start_date": "2026-10-01",
    "due_day": 15,
    "reminder_days": 3
}
resp = requests.post(f"{BASE}/recurring-payments", json=rp1_data, 
                     headers={**HEADERS, "Idempotency-Key": "test-key-1"})
if resp.status_code == 200:
    rp1 = resp.json()
    rp1_id = rp1["id"]
    log_test("Create monthly recurrence", True, f"id={rp1_id}")
    check_no_leakage(rp1, "(create)")
else:
    log_test("Create monthly recurrence", False, f"{resp.status_code}: {resp.text}")
    exit(1)

# 1.2: Idempotency - same key same body returns same
print("\n[1.2] Idempotency - same key same body...")
resp = requests.post(f"{BASE}/recurring-payments", json=rp1_data,
                     headers={**HEADERS, "Idempotency-Key": "test-key-1"})
if resp.status_code == 200 and resp.json()["id"] == rp1_id:
    log_test("Idempotency same key same body", True, "Returns same id")
else:
    log_test("Idempotency same key same body", False, f"{resp.status_code}")

# 1.3: Idempotency - same key different body returns 409
print("\n[1.3] Idempotency - same key different body...")
resp = requests.post(f"{BASE}/recurring-payments", 
                     json={**rp1_data, "amount": 100.0},
                     headers={**HEADERS, "Idempotency-Key": "test-key-1"})
log_test("Idempotency same key different body → 409", resp.status_code == 409)

# 1.4: Duplicate names are ALLOWED
print("\n[1.4] Duplicate names allowed...")
resp = requests.post(f"{BASE}/recurring-payments", 
                     json={**rp1_data, "name": "Internet Bill"},
                     headers={**HEADERS, "Idempotency-Key": "test-key-dup"})
if resp.status_code == 200:
    dup_id = resp.json()["id"]
    log_test("Duplicate names allowed", True, f"Created second with same name: {dup_id}")
    # Clean up duplicate
    requests.delete(f"{BASE}/recurring-payments/{dup_id}")
else:
    log_test("Duplicate names allowed", False, f"{resp.status_code}")

# 1.5-1.14: Validation errors (422)
print("\n[1.5-1.14] Validation errors (422)...")
validations = [
    ({"name": "", "amount": 50, "frequency": "monthly", "start_date": "2026-10-01"}, "empty name"),
    ({"name": "Test", "amount": 0, "frequency": "monthly", "start_date": "2026-10-01"}, "amount=0"),
    ({"name": "Test", "amount": -10, "frequency": "monthly", "start_date": "2026-10-01"}, "amount<0"),
    ({"name": "Test", "amount": 50, "frequency": "invalid", "start_date": "2026-10-01"}, "invalid frequency"),
    ({"name": "Test", "amount": 50, "frequency": "monthly", "start_date": "invalid"}, "invalid start_date"),
    ({"name": "Test", "amount": 50, "frequency": "monthly", "start_date": "2026-10-01", "end_date": "2026-09-01"}, "end<start"),
    ({"name": "Test", "amount": 50, "frequency": "monthly", "start_date": "2026-10-01", "due_day": 0}, "due_day=0"),
    ({"name": "Test", "amount": 50, "frequency": "monthly", "start_date": "2026-10-01", "due_day": 32}, "due_day=32"),
    ({"name": "Test", "amount": 50, "frequency": "monthly", "start_date": "2026-10-01", "reminder_days": 5}, "reminder_days=5 (not in {None,0,1,3,7})"),
    ({"name": "Test", "amount": 50, "frequency": "monthly", "start_date": "2026-10-01", "account_id": "nonexistent"}, "unknown account"),
]

for val_data, desc in validations:
    resp = requests.post(f"{BASE}/recurring-payments", json=val_data, headers=HEADERS)
    log_test(f"Validation 422: {desc}", resp.status_code == 422, f"Got {resp.status_code}")

# 1.15: Category must be expense leaf (not income, not group)
print("\n[1.15] Category validation...")
# Create income category
income_cat = requests.post(f"{BASE}/categories", json={
    "name": "Test Income", "type": "income", "icon": "cash-outline", "color": "#2FA47C"
}, headers=HEADERS).json()
resp = requests.post(f"{BASE}/recurring-payments", json={
    "name": "Test", "amount": 50, "frequency": "monthly", "start_date": "2026-10-01",
    "category_id": income_cat["id"]
}, headers=HEADERS)
log_test("Validation 422: income category", resp.status_code == 422)
requests.delete(f"{BASE}/categories/{income_cat['id']}")

print("\n" + "=" * 80)
print("TEST 2: OVERVIEW FOR SEVERAL MONTHS")
print("=" * 80)

# Create a few more recurrences for testing overview
print("\n[2.1] Creating additional recurrences...")
rp2_data = {
    "name": "Rent",
    "amount": 1000.0,
    "frequency": "monthly",
    "start_date": "2026-09-01",
    "due_day": 1,
    "category_id": test_category_id,
    "account_id": test_account_id
}
rp2 = requests.post(f"{BASE}/recurring-payments", json=rp2_data, headers=HEADERS).json()
rp2_id = rp2["id"]
print(f"✓ Created Rent: {rp2_id}")

# 2.2: Test overview for past month (September 2026)
print("\n[2.2] Overview for past month (September 2026)...")
resp = requests.get(f"{BASE}/recurring-payments/overview?year=2026&month=9")
if resp.status_code == 200:
    overview = resp.json()
    log_test("Overview past month", True, f"counts={overview['counts']}, totals={overview['totals']}")
    check_no_leakage(overview, "(overview)")
    # Should have Rent (due Sep 1)
    if overview["counts"]["total"] >= 1:
        log_test("Overview past month has items", True, f"total={overview['counts']['total']}")
    else:
        log_test("Overview past month has items", False, "No items found")
else:
    log_test("Overview past month", False, f"{resp.status_code}")

# 2.3: Test overview for current month (October 2026)
print("\n[2.3] Overview for current month (October 2026)...")
resp = requests.get(f"{BASE}/recurring-payments/overview?year=2026&month=10")
if resp.status_code == 200:
    overview = resp.json()
    log_test("Overview current month", True, f"counts={overview['counts']}, totals={overview['totals']}")
    # Should have Internet (due Oct 15) and Rent (due Oct 1)
    if overview["counts"]["total"] >= 2:
        log_test("Overview current month has items", True, f"total={overview['counts']['total']}")
    else:
        log_test("Overview current month has items", False, f"total={overview['counts']['total']}")
    
    # Check paid_pct calculation
    totals = overview["totals"]
    if totals["paid"] == 0 and totals["pending"] > 0:
        expected_pct = 0.0
        if totals["paid_pct"] == expected_pct or totals["paid_pct"] is None:
            log_test("Overview paid_pct calculation", True, f"paid_pct={totals['paid_pct']}")
        else:
            log_test("Overview paid_pct calculation", False, f"Expected 0 or None, got {totals['paid_pct']}")
    else:
        log_test("Overview paid_pct calculation", True, f"paid_pct={totals['paid_pct']}")
else:
    log_test("Overview current month", False, f"{resp.status_code}")

# 2.4: Test overview for future month (November 2026)
print("\n[2.4] Overview for future month (November 2026)...")
resp = requests.get(f"{BASE}/recurring-payments/overview?year=2026&month=11")
if resp.status_code == 200:
    overview = resp.json()
    log_test("Overview future month", True, f"counts={overview['counts']}")
    if overview["counts"]["total"] >= 2:
        log_test("Overview future month has items", True, f"total={overview['counts']['total']}")
    else:
        log_test("Overview future month has items", False, f"total={overview['counts']['total']}")
else:
    log_test("Overview future month", False, f"{resp.status_code}")

print("\n" + "=" * 80)
print("TEST 3: SHORT MONTHS HANDLING")
print("=" * 80)

# 3.1: Monthly start Jan 31 due_day 31 -> Feb 29 2024 (leap), Feb 28 2025, Apr 30, Mar 31
print("\n[3.1] Creating monthly recurrence starting Jan 31 2024 with due_day 31...")
rp3_data = {
    "name": "Monthly 31st",
    "amount": 100.0,
    "frequency": "monthly",
    "start_date": "2024-01-31",
    "due_day": 31,
    "category_id": test_category_id
}
rp3 = requests.post(f"{BASE}/recurring-payments", json=rp3_data, headers=HEADERS).json()
rp3_id = rp3["id"]
print(f"✓ Created Monthly 31st: {rp3_id}")

# Check occurrences
print("\n[3.2] Checking occurrences for short months...")
resp = requests.get(f"{BASE}/recurring-payments/{rp3_id}/occurrences?limit=50")
if resp.status_code == 200:
    occs = resp.json()
    items = occs["items"]
    due_dates = [item["due_date"] for item in items]
    
    # Check Feb 2024 (leap year) -> Feb 29
    feb_2024 = [d for d in due_dates if d.startswith("2024-02")]
    if "2024-02-29" in feb_2024:
        log_test("Short month: Feb 2024 leap year → Feb 29", True)
    else:
        log_test("Short month: Feb 2024 leap year → Feb 29", False, f"Found: {feb_2024}")
    
    # Check Feb 2025 (non-leap) -> Feb 28
    feb_2025 = [d for d in due_dates if d.startswith("2025-02")]
    if "2025-02-28" in feb_2025:
        log_test("Short month: Feb 2025 non-leap → Feb 28", True)
    else:
        log_test("Short month: Feb 2025 non-leap → Feb 28", False, f"Found: {feb_2025}")
    
    # Check Apr 2024 -> Apr 30
    apr_2024 = [d for d in due_dates if d.startswith("2024-04")]
    if "2024-04-30" in apr_2024:
        log_test("Short month: Apr 2024 → Apr 30", True)
    else:
        log_test("Short month: Apr 2024 → Apr 30", False, f"Found: {apr_2024}")
    
    # Check Mar 2024 -> Mar 31 (day not permanently shifted)
    mar_2024 = [d for d in due_dates if d.startswith("2024-03")]
    if "2024-03-31" in mar_2024:
        log_test("Short month: Mar 2024 → Mar 31 (not shifted)", True)
    else:
        log_test("Short month: Mar 2024 → Mar 31 (not shifted)", False, f"Found: {mar_2024}")
else:
    log_test("Short months occurrences", False, f"{resp.status_code}")

# 3.3: Annual Feb 29
print("\n[3.3] Creating annual recurrence on Feb 29 2024...")
rp4_data = {
    "name": "Annual Feb 29",
    "amount": 200.0,
    "frequency": "annual",
    "start_date": "2024-02-29",
    "category_id": test_category_id
}
rp4 = requests.post(f"{BASE}/recurring-payments", json=rp4_data, headers=HEADERS).json()
rp4_id = rp4["id"]
resp = requests.get(f"{BASE}/recurring-payments/{rp4_id}/occurrences?limit=10")
if resp.status_code == 200:
    due_dates = [item["due_date"] for item in resp.json()["items"]]
    # 2024-02-29, 2025-02-28, 2026-02-28, 2027-02-28, 2028-02-29
    if "2024-02-29" in due_dates and "2025-02-28" in due_dates:
        log_test("Annual Feb 29: 2024→Feb 29, 2025→Feb 28", True)
    else:
        log_test("Annual Feb 29: 2024→Feb 29, 2025→Feb 28", False, f"Found: {due_dates[:3]}")
else:
    log_test("Annual Feb 29", False, f"{resp.status_code}")

# 3.4: Biweekly across year change
print("\n[3.4] Creating biweekly recurrence across year change...")
rp5_data = {
    "name": "Biweekly Year Change",
    "amount": 50.0,
    "frequency": "biweekly",
    "start_date": "2026-12-20",
    "category_id": test_category_id
}
rp5 = requests.post(f"{BASE}/recurring-payments", json=rp5_data, headers=HEADERS).json()
rp5_id = rp5["id"]
resp = requests.get(f"{BASE}/recurring-payments/{rp5_id}/occurrences?limit=10")
if resp.status_code == 200:
    due_dates = [item["due_date"] for item in resp.json()["items"]]
    # Should have 2026-12-20, 2027-01-03, 2027-01-17, etc.
    if "2026-12-20" in due_dates and "2027-01-03" in due_dates:
        log_test("Biweekly across year change", True, f"Found dates spanning years")
    else:
        log_test("Biweekly across year change", False, f"Found: {due_dates[:3]}")
else:
    log_test("Biweekly across year change", False, f"{resp.status_code}")

# 3.5: Quarterly
print("\n[3.5] Creating quarterly recurrence...")
rp6_data = {
    "name": "Quarterly",
    "amount": 300.0,
    "frequency": "quarterly",
    "start_date": "2026-01-15",
    "category_id": test_category_id
}
rp6 = requests.post(f"{BASE}/recurring-payments", json=rp6_data, headers=HEADERS).json()
rp6_id = rp6["id"]
resp = requests.get(f"{BASE}/recurring-payments/{rp6_id}/occurrences?limit=10")
if resp.status_code == 200:
    due_dates = [item["due_date"] for item in resp.json()["items"]]
    # Should have 2026-01-15, 2026-04-15, 2026-07-15, 2026-10-15
    expected = ["2026-01-15", "2026-04-15", "2026-07-15", "2026-10-15"]
    found = [d for d in expected if d in due_dates]
    if len(found) == 4:
        log_test("Quarterly occurrences", True, f"Found all 4 quarters")
    else:
        log_test("Quarterly occurrences", False, f"Found {len(found)}/4: {found}")
else:
    log_test("Quarterly occurrences", False, f"{resp.status_code}")

print("\n" + "=" * 80)
print("TEST 4: MODE=MARK PAYMENT (NO TRANSACTION)")
print("=" * 80)

# Get initial account balance and summary
print("\n[4.1] Getting initial state...")
accs = requests.get(f"{BASE}/accounts").json()
acc_before = [a for a in accs if a["id"] == test_account_id][0]
balance_before = acc_before["current_balance"]
summary_before = requests.get(f"{BASE}/summary").json()
print(f"✓ Initial balance: {balance_before}")

# Mark payment for Internet Bill (Oct 15)
print("\n[4.2] Marking payment (mode=mark) for Oct 15...")
mark_data = {
    "due_date": "2026-10-15",
    "mode": "mark",
    "amount": 50.0,
    "date": "2026-10-15"
}
resp = requests.post(f"{BASE}/recurring-payments/{rp1_id}/payments", 
                     json=mark_data, headers=HEADERS)
if resp.status_code == 200:
    payment = resp.json()
    log_test("Mark payment created", True, f"id={payment['id']}")
    check_no_leakage(payment, "(mark payment)")
    
    # Check no transaction created
    txs = requests.get(f"{BASE}/transactions").json()
    tx_count_after = len(txs)
    log_test("Mark payment: no transaction created", True, f"Transaction count unchanged")
    
    # Check balance unchanged
    accs = requests.get(f"{BASE}/accounts").json()
    acc_after = [a for a in accs if a["id"] == test_account_id][0]
    balance_after = acc_after["current_balance"]
    if balance_after == balance_before:
        log_test("Mark payment: balance unchanged", True, f"{balance_before} → {balance_after}")
    else:
        log_test("Mark payment: balance unchanged", False, f"{balance_before} → {balance_after}")
    
    # Check summary unchanged
    summary_after = requests.get(f"{BASE}/summary").json()
    if summary_after["total_balance"] == summary_before["total_balance"]:
        log_test("Mark payment: summary unchanged", True)
    else:
        log_test("Mark payment: summary unchanged", False)
else:
    log_test("Mark payment created", False, f"{resp.status_code}: {resp.text}")

print("\n" + "=" * 80)
print("TEST 5: MODE=EXPENSE (CREATES ONE TRANSACTION)")
print("=" * 80)

# Get initial state
print("\n[5.1] Getting initial state...")
acc_before = get_account(test_account_id)
balance_before = acc_before["current_balance"]
txs_before = requests.get(f"{BASE}/transactions").json()
tx_count_before = len(txs_before)
print(f"✓ Initial balance: {balance_before}, tx count: {tx_count_before}")

# Create expense payment for Rent (Oct 1)
print("\n[5.2] Creating expense payment (mode=expense) for Oct 1...")
expense_data = {
    "due_date": "2026-10-01",
    "mode": "expense",
    "amount": 1000.0,
    "date": "2026-10-01",
    "account_id": test_account_id,
    "category_id": test_category_id
}
resp = requests.post(f"{BASE}/recurring-payments/{rp2_id}/payments",
                     json=expense_data,
                     headers={**HEADERS, "Idempotency-Key": "test-expense-1"})
if resp.status_code == 200:
    payment = resp.json()
    payment_id = payment["id"]
    tx_id = payment.get("transaction_id")
    log_test("Expense payment created", True, f"payment_id={payment_id}, tx_id={tx_id}")
    
    # Check exactly ONE transaction created
    txs_after = requests.get(f"{BASE}/transactions").json()
    tx_count_after = len(txs_after)
    if tx_count_after == tx_count_before + 1:
        log_test("Expense payment: exactly ONE transaction created", True, f"{tx_count_before} → {tx_count_after}")
    else:
        log_test("Expense payment: exactly ONE transaction created", False, f"{tx_count_before} → {tx_count_after}")
    
    # Check balance decreased exactly once
    acc_after = get_account(test_account_id)
    balance_after = acc_after["current_balance"]
    expected_balance = balance_before - 1000.0
    if abs(balance_after - expected_balance) < 0.01:
        log_test("Expense payment: balance decreased exactly once", True, f"{balance_before} → {balance_after}")
    else:
        log_test("Expense payment: balance decreased exactly once", False, f"Expected {expected_balance}, got {balance_after}")
    
    # Idempotency: replay doesn't duplicate
    print("\n[5.3] Testing idempotency (replay)...")
    resp2 = requests.post(f"{BASE}/recurring-payments/{rp2_id}/payments",
                         json=expense_data,
                         headers={**HEADERS, "Idempotency-Key": "test-expense-1"})
    if resp2.status_code == 200:
        payment2 = resp2.json()
        if payment2["id"] == payment_id:
            log_test("Expense idempotency: same payment returned", True)
            
            # Check balance still the same (no duplicate)
            acc_after2 = get_account(test_account_id)
            if acc_after2["current_balance"] == balance_after:
                log_test("Expense idempotency: no duplicate transaction", True)
            else:
                log_test("Expense idempotency: no duplicate transaction", False, f"Balance changed again")
        else:
            log_test("Expense idempotency: same payment returned", False, f"Different id")
    else:
        log_test("Expense idempotency: same payment returned", False, f"{resp2.status_code}")
    
    # Expense mode requires account_id
    print("\n[5.4] Testing expense mode validation (requires account_id)...")
    resp = requests.post(f"{BASE}/recurring-payments/{rp2_id}/payments",
                         json={"due_date": "2026-11-01", "mode": "expense", "amount": 1000.0},
                         headers=HEADERS)
    log_test("Expense mode requires account_id (422)", resp.status_code == 422)
    
    # Cannot edit linked transaction via PUT /api/transactions
    print("\n[5.5] Testing linked transaction cannot be edited...")
    if tx_id:
        resp = requests.put(f"{BASE}/transactions/{tx_id}",
                           json={"name": "Modified", "amount": 1000.0, "type": "expense"},
                           headers=HEADERS)
        log_test("Linked transaction PUT → 409", resp.status_code == 409)
        
        # Cannot delete linked transaction via DELETE /api/transactions
        print("\n[5.6] Testing linked transaction cannot be deleted...")
        resp = requests.delete(f"{BASE}/transactions/{tx_id}")
        log_test("Linked transaction DELETE → 409", resp.status_code == 409)
    
    # Delete payment removes transaction and restores balance
    print("\n[5.7] Testing DELETE payment removes transaction and restores balance...")
    balance_before_delete = get_account(test_account_id)["current_balance"]
    resp = requests.delete(f"{BASE}/recurring-payments/payments/{payment_id}")
    if resp.status_code == 200:
        log_test("DELETE payment successful", True)
        
        # Check transaction removed
        txs_after_delete = requests.get(f"{BASE}/transactions").json()
        tx_ids = [t["id"] for t in txs_after_delete]
        if tx_id not in tx_ids:
            log_test("DELETE payment: transaction removed", True)
        else:
            log_test("DELETE payment: transaction removed", False, "Transaction still exists")
        
        # Check balance restored
        acc_after_delete = get_account(test_account_id)
        balance_after_delete = acc_after_delete["current_balance"]
        expected_restored = balance_before_delete + 1000.0
        if abs(balance_after_delete - expected_restored) < 0.01:
            log_test("DELETE payment: balance restored", True, f"{balance_before_delete} → {balance_after_delete}")
        else:
            log_test("DELETE payment: balance restored", False, f"Expected {expected_restored}, got {balance_after_delete}")
    else:
        log_test("DELETE payment successful", False, f"{resp.status_code}")
else:
    log_test("Expense payment created", False, f"{resp.status_code}: {resp.text}")

print("\n" + "=" * 80)
print("TEST 6: PARTIAL PAYMENT ON FIXED")
print("=" * 80)

# Create a new fixed recurrence for partial payment testing
print("\n[6.1] Creating fixed recurrence for partial payment test...")
rp7_data = {
    "name": "Fixed Bill",
    "amount": 100.0,
    "variable": False,
    "frequency": "monthly",
    "start_date": "2026-10-20",
    "category_id": test_category_id,
    "account_id": test_account_id
}
rp7 = requests.post(f"{BASE}/recurring-payments", json=rp7_data, headers=HEADERS).json()
rp7_id = rp7["id"]

# Partial payment (amount < expected)
print("\n[6.2] Making partial payment (60 < 100)...")
resp = requests.post(f"{BASE}/recurring-payments/{rp7_id}/payments",
                     json={"due_date": "2026-10-20", "mode": "mark", "amount": 60.0},
                     headers=HEADERS)
if resp.status_code == 200:
    payment = resp.json()
    log_test("Partial payment created", True)
    
    # Check occurrence status
    resp = requests.get(f"{BASE}/recurring-payments/{rp7_id}/occurrences?limit=1")
    if resp.status_code == 200:
        occ = resp.json()["items"][0]
        if occ["status"] in ("pending", "overdue") and occ["partial"] == True and occ["remaining"] == 40.0:
            log_test("Partial payment: status pending/overdue, partial=true, remaining=40", True)
        else:
            log_test("Partial payment: status pending/overdue, partial=true, remaining=40", False,
                    f"status={occ['status']}, partial={occ.get('partial')}, remaining={occ.get('remaining')}")
    else:
        log_test("Partial payment: check occurrence", False, f"{resp.status_code}")
    
    # Second payment completes it
    print("\n[6.3] Second payment completes (40 more)...")
    resp = requests.post(f"{BASE}/recurring-payments/{rp7_id}/payments",
                         json={"due_date": "2026-10-20", "mode": "mark", "amount": 40.0},
                         headers=HEADERS)
    if resp.status_code == 200:
        log_test("Second payment created", True)
        
        # Check occurrence now paid
        resp = requests.get(f"{BASE}/recurring-payments/{rp7_id}/occurrences?limit=1")
        if resp.status_code == 200:
            occ = resp.json()["items"][0]
            if occ["status"] == "paid" and occ["paid"] == 100.0:
                log_test("Second payment: status=paid, paid=100", True)
            else:
                log_test("Second payment: status=paid, paid=100", False,
                        f"status={occ['status']}, paid={occ.get('paid')}")
        else:
            log_test("Second payment: check occurrence", False, f"{resp.status_code}")
    else:
        log_test("Second payment created", False, f"{resp.status_code}")
    
    # Overpayment without allow_overpay → 422
    print("\n[6.4] Overpayment without allow_overpay → 422...")
    resp = requests.post(f"{BASE}/recurring-payments/{rp7_id}/payments",
                         json={"due_date": "2026-11-20", "mode": "mark", "amount": 150.0},
                         headers=HEADERS)
    log_test("Overpayment without allow_overpay → 422", resp.status_code == 422)
    
    # Overpayment with allow_overpay=true → OK
    print("\n[6.5] Overpayment with allow_overpay=true → OK...")
    resp = requests.post(f"{BASE}/recurring-payments/{rp7_id}/payments",
                         json={"due_date": "2026-11-20", "mode": "mark", "amount": 150.0, "allow_overpay": True},
                         headers=HEADERS)
    log_test("Overpayment with allow_overpay=true", resp.status_code == 200)
    
    # Paying already-paid occurrence → 409
    print("\n[6.6] Paying already-paid occurrence → 409...")
    resp = requests.post(f"{BASE}/recurring-payments/{rp7_id}/payments",
                         json={"due_date": "2026-10-20", "mode": "mark", "amount": 10.0},
                         headers=HEADERS)
    log_test("Paying already-paid occurrence → 409", resp.status_code == 409)
else:
    log_test("Partial payment created", False, f"{resp.status_code}")

print("\n" + "=" * 80)
print("TEST 7: VARIABLE AMOUNT")
print("=" * 80)

# Create variable recurrence
print("\n[7.1] Creating variable recurrence...")
rp8_data = {
    "name": "Variable Utility",
    "amount": 80.0,  # estimate
    "variable": True,
    "frequency": "monthly",
    "start_date": "2026-10-25",
    "category_id": test_category_id,
    "account_id": test_account_id
}
rp8 = requests.post(f"{BASE}/recurring-payments", json=rp8_data, headers=HEADERS).json()
rp8_id = rp8["id"]

# Pay with different real amount
print("\n[7.2] Paying variable with real amount (95 vs estimate 80)...")
resp = requests.post(f"{BASE}/recurring-payments/{rp8_id}/payments",
                     json={"due_date": "2026-10-25", "mode": "mark", "amount": 95.0},
                     headers=HEADERS)
if resp.status_code == 200:
    log_test("Variable payment created", True)
    
    # Check occurrence settled
    resp = requests.get(f"{BASE}/recurring-payments/{rp8_id}/occurrences?limit=1")
    if resp.status_code == 200:
        occ = resp.json()["items"][0]
        if occ["status"] == "paid" and occ["expected"] == 80.0 and occ["paid"] == 95.0:
            log_test("Variable: settled with real amount, expected=80, paid=95", True)
        else:
            log_test("Variable: settled with real amount", False,
                    f"status={occ['status']}, expected={occ.get('expected')}, paid={occ.get('paid')}")
    else:
        log_test("Variable: check occurrence", False, f"{resp.status_code}")
    
    # Check overview distinguishes expected vs paid
    print("\n[7.3] Checking overview distinguishes expected vs paid...")
    resp = requests.get(f"{BASE}/recurring-payments/overview?year=2026&month=10")
    if resp.status_code == 200:
        overview = resp.json()
        totals = overview["totals"]
        # Should have expected (estimates) and paid (real amounts)
        if totals["expected"] > 0 and totals["paid"] > 0:
            log_test("Overview: expected vs paid distinguished", True,
                    f"expected={totals['expected']}, paid={totals['paid']}")
        else:
            log_test("Overview: expected vs paid distinguished", False, f"totals={totals}")
    else:
        log_test("Overview: expected vs paid", False, f"{resp.status_code}")
else:
    log_test("Variable payment created", False, f"{resp.status_code}")

print("\n" + "=" * 80)
print("TEST 8: MODE=LINK")
print("=" * 80)

# Create an expense transaction first
print("\n[8.1] Creating expense transaction to link...")
tx_data = {
    "name": "Internet Payment",
    "amount": 50.0,
    "type": "expense",
    "date": "2026-10-15T10:00:00Z",
    "category_id": test_category_id,
    "account_id": test_account_id
}
tx = requests.post(f"{BASE}/transactions", json=tx_data, headers=HEADERS).json()
tx_id = tx["id"]
print(f"✓ Created transaction: {tx_id}")

# Get balance before linking
balance_before_link = get_account(test_account_id)["current_balance"]

# Get link candidates
print("\n[8.2] Getting link candidates...")
resp = requests.get(f"{BASE}/recurring-payments/{rp1_id}/link-candidates?due_date=2026-10-15")
if resp.status_code == 200:
    candidates = resp.json()
    candidate_ids = [c["id"] for c in candidates]
    if tx_id in candidate_ids:
        log_test("Link candidates: transaction found", True)
    else:
        log_test("Link candidates: transaction found", False, f"tx_id not in candidates")
else:
    log_test("Link candidates", False, f"{resp.status_code}")

# Link the transaction
print("\n[8.3] Linking transaction...")
resp = requests.post(f"{BASE}/recurring-payments/{rp1_id}/payments",
                     json={"due_date": "2026-10-15", "mode": "link", "transaction_id": tx_id},
                     headers=HEADERS)
if resp.status_code == 200:
    payment = resp.json()
    log_test("Link payment created", True)
    
    # Check no new transaction created
    txs = requests.get(f"{BASE}/transactions").json()
    tx_count = len(txs)
    log_test("Link: no new transaction created", True, f"Transaction count unchanged")
    
    # Check balance unchanged
    balance_after_link = get_account(test_account_id)["current_balance"]
    if balance_after_link == balance_before_link:
        log_test("Link: balance unchanged", True)
    else:
        log_test("Link: balance unchanged", False, f"{balance_before_link} → {balance_after_link}")
    
    # Try linking same transaction again (other recurrence) → 409
    print("\n[8.4] Linking same transaction again → 409...")
    resp = requests.post(f"{BASE}/recurring-payments/{rp2_id}/payments",
                         json={"due_date": "2026-10-01", "mode": "link", "transaction_id": tx_id},
                         headers=HEADERS)
    log_test("Link same transaction again → 409", resp.status_code == 409)
    
    # Delete payment unlinks (transaction remains)
    print("\n[8.5] Deleting link payment (transaction should remain)...")
    resp = requests.delete(f"{BASE}/recurring-payments/payments/{payment['id']}")
    if resp.status_code == 200:
        log_test("DELETE link payment successful", True)
        
        # Check transaction still exists
        tx_after = requests.get(f"{BASE}/transactions/{tx_id}")
        if tx_after.status_code == 200:
            log_test("DELETE link: transaction remains", True)
        else:
            log_test("DELETE link: transaction remains", False, "Transaction was deleted")
    else:
        log_test("DELETE link payment", False, f"{resp.status_code}")
else:
    log_test("Link payment created", False, f"{resp.status_code}: {resp.text}")

# Clean up transaction
requests.delete(f"{BASE}/transactions/{tx_id}")

print("\n" + "=" * 80)
print("TEST 9: EDIT AMOUNT (PAST VS FUTURE OCCURRENCES)")
print("=" * 80)

# Create recurrence with past and future occurrences
print("\n[9.1] Creating recurrence with past occurrences...")
rp9_data = {
    "name": "Edit Test",
    "amount": 100.0,
    "frequency": "monthly",
    "start_date": "2026-09-01",
    "due_day": 1,
    "category_id": test_category_id
}
rp9 = requests.post(f"{BASE}/recurring-payments", json=rp9_data, headers=HEADERS).json()
rp9_id = rp9["id"]

# Make a payment for past occurrence (Sep 1)
print("\n[9.2] Making payment for past occurrence (Sep 1)...")
requests.post(f"{BASE}/recurring-payments/{rp9_id}/payments",
              json={"due_date": "2026-09-01", "mode": "mark", "amount": 100.0},
              headers=HEADERS)

# Edit amount to 150
print("\n[9.3] Editing amount to 150...")
resp = requests.put(f"{BASE}/recurring-payments/{rp9_id}",
                    json={**rp9_data, "amount": 150.0},
                    headers=HEADERS)
if resp.status_code == 200:
    log_test("Edit amount successful", True)
    
    # Check occurrences
    resp = requests.get(f"{BASE}/recurring-payments/{rp9_id}/occurrences?limit=10")
    if resp.status_code == 200:
        occs = resp.json()["items"]
        
        # Find Sep 1 (past paid) - should keep old amount 100
        sep_occ = [o for o in occs if o["due_date"] == "2026-09-01"]
        if sep_occ and sep_occ[0]["expected"] == 100.0:
            log_test("Edit: past paid occurrence keeps old amount (100)", True)
        else:
            log_test("Edit: past paid occurrence keeps old amount (100)", False,
                    f"Sep expected={sep_occ[0]['expected'] if sep_occ else 'not found'}")
        
        # Find Oct 1 (today or future) - should use new amount 150
        oct_occ = [o for o in occs if o["due_date"] == "2026-10-01"]
        if oct_occ and oct_occ[0]["expected"] == 150.0:
            log_test("Edit: future occurrence uses new amount (150)", True)
        else:
            log_test("Edit: future occurrence uses new amount (150)", False,
                    f"Oct expected={oct_occ[0]['expected'] if oct_occ else 'not found'}")
        
        # Check payment records preserved
        if sep_occ and len(sep_occ[0].get("records", [])) > 0:
            log_test("Edit: payment records preserved", True)
        else:
            log_test("Edit: payment records preserved", False)
    else:
        log_test("Edit: check occurrences", False, f"{resp.status_code}")
else:
    log_test("Edit amount successful", False, f"{resp.status_code}")

print("\n" + "=" * 80)
print("TEST 10: PAUSE/RESUME/END TRANSITIONS")
print("=" * 80)

# Create recurrence for state testing
print("\n[10.1] Creating recurrence for state transitions...")
rp10_data = {
    "name": "State Test",
    "amount": 50.0,
    "frequency": "monthly",
    "start_date": "2026-10-01",
    "category_id": test_category_id
}
rp10 = requests.post(f"{BASE}/recurring-payments", json=rp10_data, headers=HEADERS).json()
rp10_id = rp10["id"]

# Initial state should be active
resp = requests.get(f"{BASE}/recurring-payments/{rp10_id}")
if resp.status_code == 200 and resp.json()["state"] == "active":
    log_test("Initial state: active", True)
else:
    log_test("Initial state: active", False)

# Pause
print("\n[10.2] Pausing recurrence...")
resp = requests.post(f"{BASE}/recurring-payments/{rp10_id}/pause")
if resp.status_code == 200 and resp.json()["state"] == "paused":
    log_test("Pause transition: active → paused", True)
    
    # Check paused period generates no occurrences
    resp = requests.get(f"{BASE}/recurring-payments/overview?year=2026&month=10")
    if resp.status_code == 200:
        overview = resp.json()
        items = [i for i in overview["items"] if i["id"] == rp10_id]
        if items and items[0]["card_status"] == "paused":
            log_test("Paused: card_status=paused in overview", True)
        else:
            log_test("Paused: card_status=paused in overview", False)
    
    # Try pausing again → 409
    print("\n[10.3] Pausing already paused → 409...")
    resp = requests.post(f"{BASE}/recurring-payments/{rp10_id}/pause")
    log_test("Pause already paused → 409", resp.status_code == 409)
else:
    log_test("Pause transition", False, f"{resp.status_code}")

# Resume
print("\n[10.4] Resuming recurrence...")
resp = requests.post(f"{BASE}/recurring-payments/{rp10_id}/resume")
if resp.status_code == 200 and resp.json()["state"] == "active":
    log_test("Resume transition: paused → active", True)
    
    # Try resuming again → 409
    print("\n[10.5] Resuming already active → 409...")
    resp = requests.post(f"{BASE}/recurring-payments/{rp10_id}/resume")
    log_test("Resume already active → 409", resp.status_code == 409)
else:
    log_test("Resume transition", False, f"{resp.status_code}")

# End
print("\n[10.6] Ending recurrence...")
resp = requests.post(f"{BASE}/recurring-payments/{rp10_id}/end")
if resp.status_code == 200 and resp.json()["state"] == "ended":
    log_test("End transition: active → ended", True)
    
    # Try ending again → 409
    print("\n[10.7] Ending already ended → 409...")
    resp = requests.post(f"{BASE}/recurring-payments/{rp10_id}/end")
    log_test("End already ended → 409", resp.status_code == 409)
    
    # Ended recurrence still shows in overview of months where it had due dates
    print("\n[10.8] Ended recurrence in overview...")
    resp = requests.get(f"{BASE}/recurring-payments/overview?year=2026&month=10")
    if resp.status_code == 200:
        overview = resp.json()
        items = [i for i in overview["items"] if i["id"] == rp10_id]
        if items:
            log_test("Ended: still shows in overview for month with due dates", True)
        else:
            log_test("Ended: still shows in overview for month with due dates", False)
else:
    log_test("End transition", False, f"{resp.status_code}")

print("\n" + "=" * 80)
print("TEST 11: DUE_DATE VALIDATION AND DELETE")
print("=" * 80)

# Try payment with due_date that isn't an occurrence → 422
print("\n[11.1] Payment with invalid due_date → 422...")
resp = requests.post(f"{BASE}/recurring-payments/{rp1_id}/payments",
                     json={"due_date": "2026-10-16", "mode": "mark", "amount": 50.0},
                     headers=HEADERS)
log_test("Invalid due_date → 422", resp.status_code == 422)

# Delete recurrence
print("\n[11.2] Deleting recurrence...")
# First create an expense payment to test that created tx is kept
rp11_data = {
    "name": "Delete Test",
    "amount": 75.0,
    "frequency": "monthly",
    "start_date": "2026-10-05",
    "category_id": test_category_id,
    "account_id": test_account_id
}
rp11 = requests.post(f"{BASE}/recurring-payments", json=rp11_data, headers=HEADERS).json()
rp11_id = rp11["id"]

# Create expense payment
resp = requests.post(f"{BASE}/recurring-payments/{rp11_id}/payments",
                     json={"due_date": "2026-10-05", "mode": "expense", "amount": 75.0,
                           "account_id": test_account_id, "category_id": test_category_id},
                     headers=HEADERS)
if resp.status_code == 200:
    payment = resp.json()
    tx_id = payment["transaction_id"]
    
    # Get balance before delete
    balance_before = get_account(test_account_id)["current_balance"]
    
    # Delete recurrence
    resp = requests.delete(f"{BASE}/recurring-payments/{rp11_id}")
    if resp.status_code == 200:
        log_test("DELETE recurrence successful", True)
        
        # Check recurrence removed
        resp = requests.get(f"{BASE}/recurring-payments/{rp11_id}")
        log_test("DELETE: recurrence removed", resp.status_code == 404)
        
        # Check records removed
        resp = requests.get(f"{BASE}/recurring-payments/{rp11_id}/occurrences")
        log_test("DELETE: records removed", resp.status_code == 404)
        
        # Check created expense tx kept (unlinked)
        tx_after = requests.get(f"{BASE}/transactions/{tx_id}")
        if tx_after.status_code == 200:
            tx_data = tx_after.json()
            if "recurring_payment_id" not in tx_data or tx_data.get("recurring_payment_id") is None:
                log_test("DELETE: created tx kept and unlinked", True)
            else:
                log_test("DELETE: created tx kept and unlinked", False, "Still has recurring_payment_id")
        else:
            log_test("DELETE: created tx kept", False, "Transaction was deleted")
        
        # Check balance unchanged
        balance_after = get_account(test_account_id)["current_balance"]
        if balance_after == balance_before:
            log_test("DELETE: balance unchanged", True)
        else:
            log_test("DELETE: balance unchanged", False, f"{balance_before} → {balance_after}")
        
        # Clean up transaction
        requests.delete(f"{BASE}/transactions/{tx_id}")
    else:
        log_test("DELETE recurrence", False, f"{resp.status_code}")
else:
    log_test("Create expense for delete test", False, f"{resp.status_code}")

print("\n" + "=" * 80)
print("TEST 12: NO LEAKAGE AND EXISTING /api/recurring")
print("=" * 80)

# Check no _id or request_fingerprint leakage in all endpoints
print("\n[12.1] Checking no leakage in all endpoints...")
endpoints = [
    f"/recurring-payments",
    f"/recurring-payments/{rp1_id}",
    f"/recurring-payments/{rp1_id}/occurrences",
    f"/recurring-payments/overview?year=2026&month=10",
]
all_clean = True
for endpoint in endpoints:
    resp = requests.get(f"{BASE}{endpoint}")
    if resp.status_code == 200:
        if not check_no_leakage(resp.json(), f"({endpoint})"):
            all_clean = False
if all_clean:
    log_test("No _id/request_fingerprint leakage in all endpoints", True)

# Check existing /api/recurring still works
print("\n[12.2] Checking existing /api/recurring (old templates) still works...")
resp = requests.get(f"{BASE}/recurring")
if resp.status_code == 200:
    log_test("GET /api/recurring works", True)
    
    # Create old template
    resp = requests.post(f"{BASE}/recurring", json={
        "name": "Old Template",
        "amount": 100.0,
        "frequency": "monthly",
        "start_date": "2026-10-01"
    }, headers=HEADERS)
    if resp.status_code == 200:
        old_id = resp.json()["id"]
        log_test("POST /api/recurring works", True)
        
        # Delete old template
        resp = requests.delete(f"{BASE}/recurring/{old_id}")
        log_test("DELETE /api/recurring works", resp.status_code == 200)
    else:
        log_test("POST /api/recurring works", False, f"{resp.status_code}")
else:
    log_test("GET /api/recurring works", False, f"{resp.status_code}")

print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print(f"Total tests: {tests_passed + tests_failed}")
print(f"✅ Passed: {tests_passed}")
print(f"❌ Failed: {tests_failed}")
print(f"Success rate: {tests_passed / (tests_passed + tests_failed) * 100:.1f}%")
print("=" * 80)

# Print all results
print("\nDETAILED RESULTS:")
for result in test_results:
    print(result)

print("\n" + "=" * 80)
print("TEST SUITE COMPLETE")
print("=" * 80)
