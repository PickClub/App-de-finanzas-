#!/usr/bin/env python3
"""
Comprehensive Bills (Facturas) API Testing
Tests against isolated instance: http://127.0.0.1:8012/api
DB: test_moneyflow_bills, replica set rs0
"""

import requests
import json
from datetime import date, timedelta
from decimal import Decimal

BASE_URL = "http://127.0.0.1:8012/api"
TODAY = "2026-10-11"  # Server's today

# Test results tracking
tests_passed = 0
tests_failed = 0
failures = []

def log_pass(test_name):
    global tests_passed
    tests_passed += 1
    print(f"✅ {test_name}")

def log_fail(test_name, reason):
    global tests_failed, failures
    tests_failed += 1
    failures.append(f"{test_name}: {reason}")
    print(f"❌ {test_name}: {reason}")

def assert_eq(actual, expected, test_name):
    if actual == expected:
        log_pass(test_name)
        return True
    else:
        log_fail(test_name, f"Expected {expected}, got {actual}")
        return False

def assert_status(response, expected_status, test_name):
    if response.status_code == expected_status:
        log_pass(test_name)
        return True
    else:
        log_fail(test_name, f"Expected status {expected_status}, got {response.status_code}. Response: {response.text[:200]}")
        return False

print("=" * 80)
print("BILLS (FACTURAS) API COMPREHENSIVE TESTING")
print("=" * 80)
print(f"Base URL: {BASE_URL}")
print(f"Server Today: {TODAY}")
print()

# Setup: Create test account and category
print("SETUP: Creating test account and category...")
acc_resp = requests.post(f"{BASE_URL}/accounts", json={
    "name": "Test Bills Account",
    "type": "checking",
    "initial_balance": 10000.0
})
if acc_resp.status_code != 200:
    print(f"❌ Failed to create test account: {acc_resp.text}")
    exit(1)
test_account_id = acc_resp.json()["id"]
print(f"✓ Created test account: {test_account_id}")

cat_resp = requests.post(f"{BASE_URL}/categories", json={
    "name": "Test Bills Category",
    "type": "expense",
    "icon": "receipt",
    "color": "#FF5733"
})
if cat_resp.status_code != 200:
    print(f"❌ Failed to create test category: {cat_resp.text}")
    exit(1)
test_category_id = cat_resp.json()["id"]
print(f"✓ Created test category: {test_category_id}")

# Create income category for validation test
income_cat_resp = requests.post(f"{BASE_URL}/categories", json={
    "name": "Test Income Category",
    "type": "income",
    "icon": "cash",
    "color": "#00FF00"
})
test_income_category_id = income_cat_resp.json()["id"]
print(f"✓ Created income category: {test_income_category_id}")
print()

# ============================================================================
# TEST 1: CRUD VALIDATION
# ============================================================================
print("=" * 80)
print("TEST 1: CRUD VALIDATION")
print("=" * 80)

# 1.1: Empty name -> 422
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "",
    "amount": 100.0,
    "due_date": "2026-11-01"
})
assert_status(resp, 422, "1.1: Empty name -> 422")

# 1.2: Amount = 0 -> 422
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Test Bill",
    "amount": 0.0,
    "due_date": "2026-11-01"
})
assert_status(resp, 422, "1.2: Amount = 0 -> 422")

# 1.3: Amount < 0 -> 422
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Test Bill",
    "amount": -50.0,
    "due_date": "2026-11-01"
})
assert_status(resp, 422, "1.3: Amount < 0 -> 422")

# 1.4: Bad date -> 422
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Test Bill",
    "amount": 100.0,
    "due_date": "2026-13-45"
})
assert_status(resp, 422, "1.4: Bad date -> 422")

# 1.5: Invalid reminder (not in {null,1,3,7}) -> 422
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Test Bill",
    "amount": 100.0,
    "due_date": "2026-11-01",
    "reminder_days": 5
})
assert_status(resp, 422, "1.5: Invalid reminder (5) -> 422")

# 1.6: Nonexistent account -> 422
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Test Bill",
    "amount": 100.0,
    "due_date": "2026-11-01",
    "account_id": "nonexistent-account-id"
})
assert_status(resp, 422, "1.6: Nonexistent account -> 422")

# 1.7: Nonexistent category -> 422
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Test Bill",
    "amount": 100.0,
    "due_date": "2026-11-01",
    "category_id": "nonexistent-category-id"
})
assert_status(resp, 422, "1.7: Nonexistent category -> 422")

# 1.8: Income category -> 422
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Test Bill",
    "amount": 100.0,
    "due_date": "2026-11-01",
    "category_id": test_income_category_id
})
assert_status(resp, 422, "1.8: Income category -> 422")

# 1.9: Nonexistent recurring_payment_id -> 422
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Test Bill",
    "amount": 100.0,
    "due_date": "2026-11-01",
    "recurring_payment_id": "nonexistent-rp-id"
})
assert_status(resp, 422, "1.9: Nonexistent recurring_payment_id -> 422")

# 1.10: Valid bill creation
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Valid Test Bill",
    "amount": 150.0,
    "due_date": "2026-11-05",
    "category_id": test_category_id,
    "account_id": test_account_id,
    "reminder_days": 3
})
if assert_status(resp, 200, "1.10: Valid bill creation -> 200"):
    test_bill_1 = resp.json()
    test_bill_1_id = test_bill_1["id"]
    assert_eq(test_bill_1["name"], "Valid Test Bill", "1.10a: Bill name correct")
    assert_eq(test_bill_1["amount"], 150.0, "1.10b: Bill amount correct")
    assert_eq(test_bill_1["status"], "pending", "1.10c: Bill status pending")

# 1.11: Idempotency-Key replay returns same bill
resp1 = requests.post(f"{BASE_URL}/bills", 
    headers={"Idempotency-Key": "test-bill-idem-1"},
    json={
        "name": "Idempotent Bill",
        "amount": 200.0,
        "due_date": "2026-11-10"
    })
if assert_status(resp1, 200, "1.11a: First idempotent bill creation -> 200"):
    bill_id_1 = resp1.json()["id"]
    
    # Replay with same key and same data
    resp2 = requests.post(f"{BASE_URL}/bills",
        headers={"Idempotency-Key": "test-bill-idem-1"},
        json={
            "name": "Idempotent Bill",
            "amount": 200.0,
            "due_date": "2026-11-10"
        })
    if assert_status(resp2, 200, "1.11b: Idempotent replay -> 200"):
        bill_id_2 = resp2.json()["id"]
        assert_eq(bill_id_1, bill_id_2, "1.11c: Same bill ID returned")

# 1.12: GET /bills/{id}
resp = requests.get(f"{BASE_URL}/bills/{test_bill_1_id}")
if assert_status(resp, 200, "1.12a: GET /bills/{id} -> 200"):
    bill = resp.json()
    assert_eq(bill["id"], test_bill_1_id, "1.12b: Bill ID matches")
    assert_eq(bill["name"], "Valid Test Bill", "1.12c: Bill name matches")

# 1.13: PUT /bills/{id} - valid update
resp = requests.put(f"{BASE_URL}/bills/{test_bill_1_id}", json={
    "name": "Updated Test Bill",
    "amount": 175.0,
    "due_date": "2026-11-05",
    "category_id": test_category_id,
    "account_id": test_account_id,
    "reminder_days": 7
})
if assert_status(resp, 200, "1.13a: PUT /bills/{id} -> 200"):
    updated_bill = resp.json()
    assert_eq(updated_bill["name"], "Updated Test Bill", "1.13b: Bill name updated")
    assert_eq(updated_bill["amount"], 175.0, "1.13c: Bill amount updated")

# 1.14: DELETE /bills/{id} (no payments yet)
resp = requests.delete(f"{BASE_URL}/bills/{test_bill_1_id}")
assert_status(resp, 200, "1.14: DELETE /bills/{id} -> 200")

print()

# ============================================================================
# TEST 2: PAYMENTS (PARTIAL, FULL, OVERPAY, IDEMPOTENCY)
# ============================================================================
print("=" * 80)
print("TEST 2: PAYMENTS")
print("=" * 80)

# Create a bill for payment tests
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Payment Test Bill",
    "amount": 500.0,
    "due_date": "2026-11-15",
    "category_id": test_category_id,
    "account_id": test_account_id
})
payment_test_bill_id = resp.json()["id"]
print(f"✓ Created payment test bill: {payment_test_bill_id}")

# Get initial account balance
acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
initial_balance = acc_resp.json()["current_balance"]
print(f"✓ Initial account balance: {initial_balance}")

# 2.1: Partial payment (200 out of 500)
resp = requests.post(f"{BASE_URL}/bills/{payment_test_bill_id}/payments", json={
    "amount": 200.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})
if assert_status(resp, 200, "2.1a: Partial payment (200/500) -> 200"):
    payment_1 = resp.json()
    payment_1_id = payment_1["id"]
    
    # Check bill status
    bill_resp = requests.get(f"{BASE_URL}/bills/{payment_test_bill_id}")
    bill = bill_resp.json()
    assert_eq(bill["status"], "pending", "2.1b: Bill status still pending")
    assert_eq(bill["partial"], True, "2.1c: Bill partial=true")
    assert_eq(bill["paid_amount"], 200.0, "2.1d: Bill paid_amount=200")
    assert_eq(bill["remaining"], 300.0, "2.1e: Bill remaining=300")
    
    # Check progress
    expected_progress = 200.0 / 500.0
    actual_progress = bill["progress"]
    if abs(actual_progress - expected_progress) < 0.01:
        log_pass("2.1f: Bill progress correct (0.4)")
    else:
        log_fail("2.1f: Bill progress correct", f"Expected {expected_progress}, got {actual_progress}")
    
    # Check account balance decreased
    acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
    new_balance = acc_resp.json()["current_balance"]
    expected_balance = initial_balance - 200.0
    assert_eq(new_balance, expected_balance, "2.1g: Account balance decreased by 200")
    
    # Check exactly ONE transaction created
    tx_resp = requests.get(f"{BASE_URL}/transactions")
    transactions = [t for t in tx_resp.json() if t.get("bill_payment_id") == payment_1_id]
    assert_eq(len(transactions), 1, "2.1h: Exactly ONE transaction created")
    if len(transactions) == 1:
        tx = transactions[0]
        assert_eq(tx["bill_id"], payment_test_bill_id, "2.1i: Transaction has bill_id")
        assert_eq(tx["bill_payment_id"], payment_1_id, "2.1j: Transaction has bill_payment_id")
        assert_eq(tx["type"], "expense", "2.1k: Transaction type is expense")
        assert_eq(tx["amount"], 200.0, "2.1l: Transaction amount is 200")

# 2.2: Second partial payment (150 more, total 350/500)
resp = requests.post(f"{BASE_URL}/bills/{payment_test_bill_id}/payments", json={
    "amount": 150.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})
if assert_status(resp, 200, "2.2a: Second partial payment (150) -> 200"):
    payment_2_id = resp.json()["id"]
    
    # Check bill status still pending
    bill_resp = requests.get(f"{BASE_URL}/bills/{payment_test_bill_id}")
    bill = bill_resp.json()
    assert_eq(bill["status"], "pending", "2.2b: Bill status still pending")
    assert_eq(bill["paid_amount"], 350.0, "2.2c: Bill paid_amount=350")
    assert_eq(bill["remaining"], 150.0, "2.2d: Bill remaining=150")

# 2.3: Final payment (150 more, total 500/500 = paid)
resp = requests.post(f"{BASE_URL}/bills/{payment_test_bill_id}/payments", json={
    "amount": 150.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})
if assert_status(resp, 200, "2.3a: Final payment (150) -> 200"):
    payment_3_id = resp.json()["id"]
    
    # Check bill status now paid
    bill_resp = requests.get(f"{BASE_URL}/bills/{payment_test_bill_id}")
    bill = bill_resp.json()
    assert_eq(bill["status"], "paid", "2.3b: Bill status now paid")
    assert_eq(bill["paid_amount"], 500.0, "2.3c: Bill paid_amount=500")
    assert_eq(bill["remaining"], 0.0, "2.3d: Bill remaining=0")
    assert_eq(bill["partial"], False, "2.3e: Bill partial=false")
    
    # Check account balance decreased by total 500
    acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
    final_balance = acc_resp.json()["current_balance"]
    expected_final = initial_balance - 500.0
    assert_eq(final_balance, expected_final, "2.3f: Account balance decreased by total 500")

# 2.4: Paying already-paid bill -> 409
resp = requests.post(f"{BASE_URL}/bills/{payment_test_bill_id}/payments", json={
    "amount": 50.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})
assert_status(resp, 409, "2.4: Paying already-paid bill -> 409")

# Create another bill for overpay test
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Overpay Test Bill",
    "amount": 100.0,
    "due_date": "2026-11-20",
    "category_id": test_category_id,
    "account_id": test_account_id
})
overpay_bill_id = resp.json()["id"]

# 2.5: Overpay (150 > 100) -> 422
resp = requests.post(f"{BASE_URL}/bills/{overpay_bill_id}/payments", json={
    "amount": 150.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})
assert_status(resp, 422, "2.5: Overpay (150 > 100) -> 422")

# 2.6: Idempotency-Key replay for payments
resp1 = requests.post(f"{BASE_URL}/bills/{overpay_bill_id}/payments",
    headers={"Idempotency-Key": "test-payment-idem-1"},
    json={
        "amount": 50.0,
        "account_id": test_account_id,
        "date": "2026-10-11"
    })
if assert_status(resp1, 200, "2.6a: First idempotent payment -> 200"):
    payment_id_1 = resp1.json()["id"]
    
    # Get balance after first payment
    acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
    balance_after_first = acc_resp.json()["current_balance"]
    
    # Replay with same key and same data
    resp2 = requests.post(f"{BASE_URL}/bills/{overpay_bill_id}/payments",
        headers={"Idempotency-Key": "test-payment-idem-1"},
        json={
            "amount": 50.0,
            "account_id": test_account_id,
            "date": "2026-10-11"
        })
    if assert_status(resp2, 200, "2.6b: Idempotent payment replay -> 200"):
        payment_id_2 = resp2.json()["id"]
        assert_eq(payment_id_1, payment_id_2, "2.6c: Same payment ID returned")
        
        # Check balance unchanged (no duplicate charge)
        acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
        balance_after_replay = acc_resp.json()["current_balance"]
        assert_eq(balance_after_first, balance_after_replay, "2.6d: Balance unchanged on replay")
        
        # Check no duplicate transaction
        tx_resp = requests.get(f"{BASE_URL}/transactions")
        transactions = [t for t in tx_resp.json() if t.get("bill_payment_id") == payment_id_1]
        assert_eq(len(transactions), 1, "2.6e: No duplicate transaction created")

# 2.7: Same idempotency key with different data -> 409
resp = requests.post(f"{BASE_URL}/bills/{overpay_bill_id}/payments",
    headers={"Idempotency-Key": "test-payment-idem-1"},
    json={
        "amount": 30.0,  # Different amount
        "account_id": test_account_id,
        "date": "2026-10-11"
    })
assert_status(resp, 409, "2.7: Same idem key, different data -> 409")

print()

# ============================================================================
# TEST 3: RECURRING BILLS (NEXT PERIOD CREATION)
# ============================================================================
print("=" * 80)
print("TEST 3: RECURRING BILLS")
print("=" * 80)

# 3.1: Monthly recurring bill due on 31st (Jan 31 -> Feb 28)
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Monthly Bill Jan 31",
    "amount": 250.0,
    "due_date": "2026-01-31",
    "frequency": "monthly",
    "category_id": test_category_id,
    "account_id": test_account_id
})
if assert_status(resp, 200, "3.1a: Create monthly bill (Jan 31) -> 200"):
    monthly_bill_id = resp.json()["id"]
    series_id = resp.json()["series_id"]
    
    # Pay the bill fully
    pay_resp = requests.post(f"{BASE_URL}/bills/{monthly_bill_id}/payments", json={
        "amount": 250.0,
        "account_id": test_account_id,
        "date": "2026-01-31"
    })
    if assert_status(pay_resp, 200, "3.1b: Pay monthly bill fully -> 200"):
        next_bill_id = pay_resp.json().get("next_bill_id")
        
        if next_bill_id:
            log_pass("3.1c: next_bill_id returned")
            
            # Check next bill created with clamped date (Feb 28, not Feb 31)
            next_bill_resp = requests.get(f"{BASE_URL}/bills/{next_bill_id}")
            if assert_status(next_bill_resp, 200, "3.1d: GET next bill -> 200"):
                next_bill = next_bill_resp.json()
                assert_eq(next_bill["due_date"], "2026-02-28", "3.1e: Next bill due_date clamped to Feb 28")
                assert_eq(next_bill["series_id"], series_id, "3.1f: Next bill has same series_id")
                assert_eq(next_bill["amount"], 250.0, "3.1g: Next bill has same amount")
                assert_eq(next_bill["name"], "Monthly Bill Jan 31", "3.1h: Next bill has same name")
            
            # Check original bill has next_bill_id set
            orig_bill_resp = requests.get(f"{BASE_URL}/bills/{monthly_bill_id}")
            orig_bill = orig_bill_resp.json()
            assert_eq(orig_bill["next_bill_id"], next_bill_id, "3.1i: Original bill next_bill_id set")
            
            # Delete the payment and pay again - should NOT create second next period
            delete_resp = requests.delete(f"{BASE_URL}/bills/payments/{pay_resp.json()['id']}")
            if assert_status(delete_resp, 200, "3.1j: Delete payment -> 200"):
                # Pay again
                pay_again_resp = requests.post(f"{BASE_URL}/bills/{monthly_bill_id}/payments", json={
                    "amount": 250.0,
                    "account_id": test_account_id,
                    "date": "2026-01-31"
                })
                if assert_status(pay_again_resp, 200, "3.1k: Pay again -> 200"):
                    next_bill_id_2 = pay_again_resp.json().get("next_bill_id")
                    assert_eq(next_bill_id, next_bill_id_2, "3.1l: Same next_bill_id (no duplicate)")
        else:
            log_fail("3.1c: next_bill_id returned", "next_bill_id is None")

# 3.2: Weekly recurring bill (adds 7 days)
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Weekly Bill",
    "amount": 50.0,
    "due_date": "2026-11-01",
    "frequency": "weekly",
    "category_id": test_category_id,
    "account_id": test_account_id
})
if assert_status(resp, 200, "3.2a: Create weekly bill -> 200"):
    weekly_bill_id = resp.json()["id"]
    
    # Pay fully
    pay_resp = requests.post(f"{BASE_URL}/bills/{weekly_bill_id}/payments", json={
        "amount": 50.0,
        "account_id": test_account_id,
        "date": "2026-11-01"
    })
    if assert_status(pay_resp, 200, "3.2b: Pay weekly bill -> 200"):
        next_bill_id = pay_resp.json().get("next_bill_id")
        if next_bill_id:
            next_bill_resp = requests.get(f"{BASE_URL}/bills/{next_bill_id}")
            next_bill = next_bill_resp.json()
            # Nov 1 + 7 days = Nov 8
            assert_eq(next_bill["due_date"], "2026-11-08", "3.2c: Weekly bill adds 7 days")

# 3.3: Quarterly recurring bill (adds 3 months)
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Quarterly Bill",
    "amount": 300.0,
    "due_date": "2026-01-15",
    "frequency": "quarterly",
    "category_id": test_category_id,
    "account_id": test_account_id
})
if assert_status(resp, 200, "3.3a: Create quarterly bill -> 200"):
    quarterly_bill_id = resp.json()["id"]
    
    # Pay fully
    pay_resp = requests.post(f"{BASE_URL}/bills/{quarterly_bill_id}/payments", json={
        "amount": 300.0,
        "account_id": test_account_id,
        "date": "2026-01-15"
    })
    if assert_status(pay_resp, 200, "3.3b: Pay quarterly bill -> 200"):
        next_bill_id = pay_resp.json().get("next_bill_id")
        if next_bill_id:
            next_bill_resp = requests.get(f"{BASE_URL}/bills/{next_bill_id}")
            next_bill = next_bill_resp.json()
            # Jan 15 + 3 months = Apr 15
            assert_eq(next_bill["due_date"], "2026-04-15", "3.3c: Quarterly bill adds 3 months")

# 3.4: Yearly recurring bill (adds 12 months)
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Yearly Bill",
    "amount": 1200.0,
    "due_date": "2026-03-01",
    "frequency": "yearly",
    "category_id": test_category_id,
    "account_id": test_account_id
})
if assert_status(resp, 200, "3.4a: Create yearly bill -> 200"):
    yearly_bill_id = resp.json()["id"]
    
    # Pay fully
    pay_resp = requests.post(f"{BASE_URL}/bills/{yearly_bill_id}/payments", json={
        "amount": 1200.0,
        "account_id": test_account_id,
        "date": "2026-03-01"
    })
    if assert_status(pay_resp, 200, "3.4b: Pay yearly bill -> 200"):
        next_bill_id = pay_resp.json().get("next_bill_id")
        if next_bill_id:
            next_bill_resp = requests.get(f"{BASE_URL}/bills/{next_bill_id}")
            next_bill = next_bill_resp.json()
            # Mar 1 2026 + 12 months = Mar 1 2027
            assert_eq(next_bill["due_date"], "2027-03-01", "3.4c: Yearly bill adds 12 months")

print()

# ============================================================================
# TEST 4: DELETE BILL PAYMENT
# ============================================================================
print("=" * 80)
print("TEST 4: DELETE BILL PAYMENT")
print("=" * 80)

# Create a bill and pay it
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Delete Payment Test",
    "amount": 400.0,
    "due_date": "2026-11-25",
    "category_id": test_category_id,
    "account_id": test_account_id
})
delete_test_bill_id = resp.json()["id"]

# Get balance before payment
acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
balance_before_payment = acc_resp.json()["current_balance"]

# Pay the bill
pay_resp = requests.post(f"{BASE_URL}/bills/{delete_test_bill_id}/payments", json={
    "amount": 400.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})
payment_to_delete_id = pay_resp.json()["id"]
transaction_id = pay_resp.json()["transaction_id"]

# Check bill is paid
bill_resp = requests.get(f"{BASE_URL}/bills/{delete_test_bill_id}")
assert_eq(bill_resp.json()["status"], "paid", "4.1: Bill status paid after payment")

# Check balance decreased
acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
balance_after_payment = acc_resp.json()["current_balance"]
assert_eq(balance_after_payment, balance_before_payment - 400.0, "4.2: Balance decreased by 400")

# Delete the payment
delete_resp = requests.delete(f"{BASE_URL}/bills/payments/{payment_to_delete_id}")
if assert_status(delete_resp, 200, "4.3: DELETE payment -> 200"):
    # Check transaction deleted
    tx_resp = requests.get(f"{BASE_URL}/transactions/{transaction_id}")
    assert_status(tx_resp, 404, "4.4: Transaction deleted")
    
    # Check balance restored
    acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
    balance_after_delete = acc_resp.json()["current_balance"]
    assert_eq(balance_after_delete, balance_before_payment, "4.5: Balance restored")
    
    # Check bill status back to pending
    bill_resp = requests.get(f"{BASE_URL}/bills/{delete_test_bill_id}")
    bill = bill_resp.json()
    assert_eq(bill["status"], "pending", "4.6: Bill status back to pending")
    assert_eq(bill["paid_amount"], 0.0, "4.7: Bill paid_amount back to 0")
    assert_eq(bill["remaining"], 400.0, "4.8: Bill remaining back to 400")

print()

# ============================================================================
# TEST 5: DELETE BILL WITH PAYMENTS
# ============================================================================
print("=" * 80)
print("TEST 5: DELETE BILL WITH PAYMENTS")
print("=" * 80)

# Create a bill and pay it
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Delete Bill Test",
    "amount": 350.0,
    "due_date": "2026-11-30",
    "category_id": test_category_id,
    "account_id": test_account_id
})
delete_bill_test_id = resp.json()["id"]

# Pay the bill
pay_resp = requests.post(f"{BASE_URL}/bills/{delete_bill_test_id}/payments", json={
    "amount": 350.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})
payment_id_for_delete = pay_resp.json()["id"]
transaction_id_for_delete = pay_resp.json()["transaction_id"]

# Get balance before delete
acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
balance_before_delete = acc_resp.json()["current_balance"]

# Delete the bill
delete_resp = requests.delete(f"{BASE_URL}/bills/{delete_bill_test_id}")
if assert_status(delete_resp, 200, "5.1: DELETE bill with payments -> 200"):
    # Check bill deleted
    bill_resp = requests.get(f"{BASE_URL}/bills/{delete_bill_test_id}")
    assert_status(bill_resp, 404, "5.2: Bill deleted")
    
    # Check transaction still exists but unlinked
    tx_resp = requests.get(f"{BASE_URL}/transactions/{transaction_id_for_delete}")
    if assert_status(tx_resp, 200, "5.3: Transaction still exists"):
        tx = tx_resp.json()
        if "bill_id" not in tx or tx.get("bill_id") is None:
            log_pass("5.4: Transaction bill_id removed")
        else:
            log_fail("5.4: Transaction bill_id removed", f"bill_id still present: {tx.get('bill_id')}")
        
        if "bill_payment_id" not in tx or tx.get("bill_payment_id") is None:
            log_pass("5.5: Transaction bill_payment_id removed")
        else:
            log_fail("5.5: Transaction bill_payment_id removed", f"bill_payment_id still present: {tx.get('bill_payment_id')}")
    
    # Check balance unchanged
    acc_resp = requests.get(f"{BASE_URL}/accounts/{test_account_id}")
    balance_after_delete = acc_resp.json()["current_balance"]
    assert_eq(balance_after_delete, balance_before_delete, "5.6: Balance unchanged after bill delete")
    
    # Check bill_payment deleted
    # (We can't directly GET a payment, but we can check via bill detail that it's gone)
    # Since bill is deleted, we'll just verify the transaction exists and is unlinked

print()

# ============================================================================
# TEST 6: TRANSACTION PROTECTION (PUT/DELETE on bill-payment transaction)
# ============================================================================
print("=" * 80)
print("TEST 6: TRANSACTION PROTECTION")
print("=" * 80)

# Create a bill and pay it
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Transaction Protection Test",
    "amount": 275.0,
    "due_date": "2026-12-05",
    "category_id": test_category_id,
    "account_id": test_account_id
})
protection_bill_id = resp.json()["id"]

# Pay the bill
pay_resp = requests.post(f"{BASE_URL}/bills/{protection_bill_id}/payments", json={
    "amount": 275.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})
protected_transaction_id = pay_resp.json()["transaction_id"]

# 6.1: Try to PUT the transaction -> 409
put_resp = requests.put(f"{BASE_URL}/transactions/{protected_transaction_id}", json={
    "name": "Modified Transaction",
    "amount": 300.0,
    "type": "expense",
    "date": "2026-10-11",
    "account_id": test_account_id,
    "category_id": test_category_id
})
assert_status(put_resp, 409, "6.1: PUT bill-payment transaction -> 409")

# 6.2: Try to DELETE the transaction -> 409
delete_resp = requests.delete(f"{BASE_URL}/transactions/{protected_transaction_id}")
assert_status(delete_resp, 409, "6.2: DELETE bill-payment transaction -> 409")

print()

# ============================================================================
# TEST 7: SUMMARY ENDPOINT
# ============================================================================
print("=" * 80)
print("TEST 7: SUMMARY ENDPOINT")
print("=" * 80)

# Get current summary
summary_resp = requests.get(f"{BASE_URL}/bills/summary")
if assert_status(summary_resp, 200, "7.1: GET /bills/summary -> 200"):
    summary = summary_resp.json()
    
    # Check structure
    if "pending" in summary and "amount" in summary["pending"] and "count" in summary["pending"]:
        log_pass("7.2: Summary has pending.amount and pending.count")
    else:
        log_fail("7.2: Summary structure", "Missing pending fields")
    
    if "overdue" in summary and "amount" in summary["overdue"] and "count" in summary["overdue"]:
        log_pass("7.3: Summary has overdue.amount and overdue.count")
    else:
        log_fail("7.3: Summary structure", "Missing overdue fields")
    
    if "paid_month" in summary and "amount" in summary["paid_month"] and "count" in summary["paid_month"]:
        log_pass("7.4: Summary has paid_month.amount and paid_month.count")
    else:
        log_fail("7.4: Summary structure", "Missing paid_month fields")
    
    if "next_due" in summary:
        log_pass("7.5: Summary has next_due")
    else:
        log_fail("7.5: Summary structure", "Missing next_due")
    
    # Verify pending includes overdue
    # pending = sum of remaining of all unpaid bills (including overdue)
    # overdue = remaining of unpaid bills with due < today
    # So pending.amount >= overdue.amount
    if summary["pending"]["amount"] >= summary["overdue"]["amount"]:
        log_pass("7.6: pending.amount >= overdue.amount")
    else:
        log_fail("7.6: pending includes overdue", f"pending={summary['pending']['amount']}, overdue={summary['overdue']['amount']}")

print()

# ============================================================================
# TEST 8: STATUS FILTERS
# ============================================================================
print("=" * 80)
print("TEST 8: STATUS FILTERS")
print("=" * 80)

# Create bills with different statuses
# Overdue bill (due in the past, unpaid)
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Overdue Bill",
    "amount": 100.0,
    "due_date": "2026-10-01",  # Past date
    "category_id": test_category_id,
    "account_id": test_account_id
})
overdue_bill_id = resp.json()["id"]

# Pending bill (due in the future, unpaid)
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Pending Bill",
    "amount": 150.0,
    "due_date": "2026-12-15",  # Future date
    "category_id": test_category_id,
    "account_id": test_account_id
})
pending_bill_id = resp.json()["id"]

# Paid bill
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Paid Bill",
    "amount": 200.0,
    "due_date": "2026-11-10",
    "category_id": test_category_id,
    "account_id": test_account_id
})
paid_bill_id = resp.json()["id"]
requests.post(f"{BASE_URL}/bills/{paid_bill_id}/payments", json={
    "amount": 200.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})

# 8.1: GET /bills?status=all
resp = requests.get(f"{BASE_URL}/bills?status=all")
if assert_status(resp, 200, "8.1a: GET /bills?status=all -> 200"):
    data = resp.json()
    if "counts" in data:
        log_pass("8.1b: Response has counts")
        counts = data["counts"]
        if "all" in counts and "pending" in counts and "paid" in counts and "overdue" in counts:
            log_pass("8.1c: Counts has all, pending, paid, overdue")
        else:
            log_fail("8.1c: Counts structure", f"Missing keys: {counts.keys()}")
    else:
        log_fail("8.1b: Response structure", "Missing counts")

# 8.2: GET /bills?status=pending
resp = requests.get(f"{BASE_URL}/bills?status=pending")
if assert_status(resp, 200, "8.2a: GET /bills?status=pending -> 200"):
    data = resp.json()
    items = data.get("items", [])
    # All items should have status=pending
    all_pending = all(item["status"] == "pending" for item in items)
    if all_pending:
        log_pass("8.2b: All items have status=pending")
    else:
        log_fail("8.2b: Filter pending", f"Found non-pending items: {[i['status'] for i in items]}")

# 8.3: GET /bills?status=paid
resp = requests.get(f"{BASE_URL}/bills?status=paid")
if assert_status(resp, 200, "8.3a: GET /bills?status=paid -> 200"):
    data = resp.json()
    items = data.get("items", [])
    # All items should have status=paid
    all_paid = all(item["status"] == "paid" for item in items)
    if all_paid:
        log_pass("8.3b: All items have status=paid")
    else:
        log_fail("8.3b: Filter paid", f"Found non-paid items: {[i['status'] for i in items]}")

# 8.4: GET /bills?status=overdue
resp = requests.get(f"{BASE_URL}/bills?status=overdue")
if assert_status(resp, 200, "8.4a: GET /bills?status=overdue -> 200"):
    data = resp.json()
    items = data.get("items", [])
    # All items should have status=overdue
    all_overdue = all(item["status"] == "overdue" for item in items)
    if all_overdue:
        log_pass("8.4b: All items have status=overdue")
    else:
        log_fail("8.4b: Filter overdue", f"Found non-overdue items: {[i['status'] for i in items]}")

# 8.5: Invalid status -> 422
resp = requests.get(f"{BASE_URL}/bills?status=invalid")
assert_status(resp, 422, "8.5: Invalid status -> 422")

print()

# ============================================================================
# TEST 9: RECURRING-PAYMENT LINK
# ============================================================================
print("=" * 80)
print("TEST 9: RECURRING-PAYMENT LINK")
print("=" * 80)

# Create a recurring payment (monthly, start date 2026-12-01)
rp_resp = requests.post(f"{BASE_URL}/recurring-payments", json={
    "name": "Linked Recurring Payment",
    "amount": 180.0,
    "category_id": test_category_id,
    "account_id": test_account_id,
    "frequency": "monthly",
    "start_date": "2026-12-01",
    "due_day": 1
})
if assert_status(rp_resp, 200, "9.1a: Create recurring payment -> 200"):
    rp_id = rp_resp.json()["id"]
    
    # Create a bill with the same due date and link to the recurring payment
    bill_resp = requests.post(f"{BASE_URL}/bills", json={
        "name": "Linked Bill",
        "amount": 180.0,
        "due_date": "2026-12-01",
        "category_id": test_category_id,
        "account_id": test_account_id,
        "recurring_payment_id": rp_id
    })
    if assert_status(bill_resp, 200, "9.1b: Create linked bill -> 200"):
        linked_bill_id = bill_resp.json()["id"]
        
        # Check calendar BEFORE payment - should show bill_due, NO recurring_due
        cal_resp = requests.get(f"{BASE_URL}/calendar/events?start=2026-11-25&end=2026-12-05")
        if assert_status(cal_resp, 200, "9.2a: GET calendar events -> 200"):
            events = cal_resp.json().get("events", [])
            
            # Find events for 2026-12-01
            dec_1_events = [e for e in events if e["date"] == "2026-12-01"]
            
            # Should have bill_due, NOT recurring_due
            bill_due_events = [e for e in dec_1_events if e.get("kind") == "bill" and e.get("subtype") == "bill_due"]
            recurring_due_events = [e for e in dec_1_events if e.get("kind") == "recurring" and e.get("subtype") == "recurring_due"]
            
            if len(bill_due_events) > 0:
                log_pass("9.2b: Calendar shows bill_due for unpaid linked bill")
            else:
                log_fail("9.2b: Calendar bill_due", f"No bill_due found for 2026-12-01. Events: {[e.get('subtype') for e in dec_1_events]}")
            
            if len(recurring_due_events) == 0:
                log_pass("9.2c: Calendar does NOT show recurring_due (hidden by unpaid bill)")
            else:
                log_fail("9.2c: Calendar recurring_due hidden", f"Found {len(recurring_due_events)} recurring_due events")
        
        # Pay the bill
        pay_resp = requests.post(f"{BASE_URL}/bills/{linked_bill_id}/payments", json={
            "amount": 180.0,
            "account_id": test_account_id,
            "date": "2026-12-01"
        })
        if assert_status(pay_resp, 200, "9.3a: Pay linked bill -> 200"):
            payment_id = pay_resp.json()["id"]
            transaction_id = pay_resp.json()["transaction_id"]
            
            # Check transaction has both bill_payment_id and recurring_record_id
            tx_resp = requests.get(f"{BASE_URL}/transactions/{transaction_id}")
            if assert_status(tx_resp, 200, "9.3b: GET transaction -> 200"):
                tx = tx_resp.json()
                
                if tx.get("bill_payment_id") == payment_id:
                    log_pass("9.3c: Transaction has bill_payment_id")
                else:
                    log_fail("9.3c: Transaction bill_payment_id", f"Expected {payment_id}, got {tx.get('bill_payment_id')}")
                
                if tx.get("recurring_record_id"):
                    log_pass("9.3d: Transaction has recurring_record_id")
                    recurring_record_id = tx["recurring_record_id"]
                else:
                    log_fail("9.3d: Transaction recurring_record_id", "Missing recurring_record_id")
                    recurring_record_id = None
                
                if tx.get("recurring_payment_id") == rp_id:
                    log_pass("9.3e: Transaction has recurring_payment_id")
                else:
                    log_fail("9.3e: Transaction recurring_payment_id", f"Expected {rp_id}, got {tx.get('recurring_payment_id')}")
            
            # Check recurring payment occurrence is paid
            rp_occ_resp = requests.get(f"{BASE_URL}/recurring-payments/{rp_id}/occurrences")
            if assert_status(rp_occ_resp, 200, "9.4a: GET recurring occurrences -> 200"):
                occurrences = rp_occ_resp.json().get("items", [])
                dec_1_occ = [o for o in occurrences if o["due_date"] == "2026-12-01"]
                
                if len(dec_1_occ) > 0:
                    occ = dec_1_occ[0]
                    if occ.get("status") == "paid":
                        log_pass("9.4b: Recurring occurrence status=paid")
                    else:
                        log_fail("9.4b: Recurring occurrence paid", f"Status: {occ.get('status')}")
                else:
                    log_fail("9.4a: Find occurrence", "No occurrence for 2026-12-01")
            
            # Check calendar AFTER payment - should show bill_paid, NO recurring_due, NO duplicate
            cal_resp = requests.get(f"{BASE_URL}/calendar/events?start=2026-11-25&end=2026-12-05")
            if assert_status(cal_resp, 200, "9.5a: GET calendar events after payment -> 200"):
                events = cal_resp.json().get("events", [])
                
                # Find events for 2026-12-01
                dec_1_events = [e for e in events if e["date"] == "2026-12-01"]
                
                # Should have bill_paid, NOT recurring_due, NOT duplicate expense
                bill_paid_events = [e for e in dec_1_events if e.get("kind") == "bill" and e.get("subtype") == "bill_paid"]
                recurring_due_events = [e for e in dec_1_events if e.get("kind") == "recurring" and e.get("subtype") == "recurring_due"]
                expense_events = [e for e in dec_1_events if e.get("kind") == "expense"]
                
                if len(bill_paid_events) == 1:
                    log_pass("9.5b: Calendar shows ONE bill_paid event")
                else:
                    log_fail("9.5b: Calendar bill_paid", f"Found {len(bill_paid_events)} bill_paid events")
                
                if len(recurring_due_events) == 0:
                    log_pass("9.5c: Calendar does NOT show recurring_due (paid)")
                else:
                    log_fail("9.5c: Calendar recurring_due", f"Found {len(recurring_due_events)} recurring_due events")
                
                # Count total expense-like events (should be 1: the bill_paid)
                total_expense_events = len(bill_paid_events) + len(expense_events)
                if total_expense_events == 1:
                    log_pass("9.5d: Only ONE expense event (no duplicate)")
                else:
                    log_fail("9.5d: No duplicate expense", f"Found {total_expense_events} expense events")
            
            # Delete the bill payment - should remove linked recurring record
            if recurring_record_id:
                delete_resp = requests.delete(f"{BASE_URL}/bills/payments/{payment_id}")
                if assert_status(delete_resp, 200, "9.6a: DELETE bill payment -> 200"):
                    # Check recurring occurrence back to pending
                    rp_occ_resp = requests.get(f"{BASE_URL}/recurring-payments/{rp_id}/occurrences")
                    if assert_status(rp_occ_resp, 200, "9.6b: GET recurring occurrences -> 200"):
                        occurrences = rp_occ_resp.json().get("items", [])
                        dec_1_occ = [o for o in occurrences if o["due_date"] == "2026-12-01"]
                        
                        if len(dec_1_occ) > 0:
                            occ = dec_1_occ[0]
                            if occ.get("status") in ("pending", "overdue"):
                                log_pass("9.6c: Recurring occurrence back to pending/overdue")
                            else:
                                log_fail("9.6c: Recurring occurrence status", f"Status: {occ.get('status')}")

print()

# ============================================================================
# TEST 10: CALENDAR INTEGRATION
# ============================================================================
print("=" * 80)
print("TEST 10: CALENDAR INTEGRATION")
print("=" * 80)

# Create an unpaid bill for calendar test
cal_bill_resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "Calendar Test Bill",
    "amount": 225.0,
    "due_date": "2026-12-10",
    "category_id": test_category_id,
    "account_id": test_account_id
})
cal_bill_id = cal_bill_resp.json()["id"]

# 10.1: Check unpaid bill appears in calendar as bill_due
cal_resp = requests.get(f"{BASE_URL}/calendar/events?start=2026-12-05&end=2026-12-15")
if assert_status(cal_resp, 200, "10.1a: GET calendar events -> 200"):
    events = cal_resp.json().get("events", [])
    
    # Find bill_due events for our bill
    bill_due_events = [e for e in events if e.get("kind") == "bill" and e.get("subtype") == "bill_due" and e.get("date") == "2026-12-10"]
    
    if len(bill_due_events) > 0:
        log_pass("10.1b: Unpaid bill appears as bill_due")
        
        # Check it has remaining amount
        event = bill_due_events[0]
        if event.get("amount") == 225.0:
            log_pass("10.1c: bill_due has correct remaining amount")
        else:
            log_fail("10.1c: bill_due amount", f"Expected 225.0, got {event.get('amount')}")
    else:
        log_fail("10.1b: Unpaid bill in calendar", "No bill_due event found")

# 10.2: Check calendar summary includes bills
cal_summary_resp = requests.get(f"{BASE_URL}/calendar/summary?year=2026&month=12")
if assert_status(cal_summary_resp, 200, "10.2a: GET calendar summary -> 200"):
    summary = cal_summary_resp.json()
    
    if "bills" in summary:
        bills_data = summary["bills"]
        
        if "amount" in bills_data and "count" in bills_data and "available" in bills_data:
            log_pass("10.2b: Calendar summary has bills.amount, bills.count, bills.available")
            
            if bills_data["available"] == True:
                log_pass("10.2c: bills.available=true")
            else:
                log_fail("10.2c: bills.available", f"Expected true, got {bills_data['available']}")
            
            # Should include our test bill (225.0)
            if bills_data["amount"] >= 225.0:
                log_pass("10.2d: bills.amount includes test bill")
            else:
                log_fail("10.2d: bills.amount", f"Expected >= 225.0, got {bills_data['amount']}")
        else:
            log_fail("10.2b: bills structure", f"Missing fields: {bills_data.keys()}")
    else:
        log_fail("10.2a: Calendar summary structure", "Missing bills")

# Pay the bill and check calendar
pay_resp = requests.post(f"{BASE_URL}/bills/{cal_bill_id}/payments", json={
    "amount": 225.0,
    "account_id": test_account_id,
    "date": "2026-12-10"
})
if assert_status(pay_resp, 200, "10.3a: Pay calendar test bill -> 200"):
    # Check calendar now shows bill_paid instead of bill_due
    cal_resp = requests.get(f"{BASE_URL}/calendar/events?start=2026-12-05&end=2026-12-15")
    if assert_status(cal_resp, 200, "10.3b: GET calendar events after payment -> 200"):
        events = cal_resp.json().get("events", [])
        
        # Should have bill_paid, NOT bill_due
        bill_paid_events = [e for e in events if e.get("kind") == "bill" and e.get("subtype") == "bill_paid" and e.get("date") == "2026-12-10"]
        bill_due_events = [e for e in events if e.get("kind") == "bill" and e.get("subtype") == "bill_due" and e.get("date") == "2026-12-10"]
        
        if len(bill_paid_events) > 0:
            log_pass("10.3c: Paid bill appears as bill_paid")
        else:
            log_fail("10.3c: Paid bill in calendar", "No bill_paid event found")
        
        # The specific bill_due for our paid bill should be gone
        # (There might be other bill_due events for other bills)
        # We can't easily distinguish, so we'll just check that bill_paid exists

# 10.4: Check calendar summary payments include bill payment
cal_summary_resp = requests.get(f"{BASE_URL}/calendar/summary?year=2026&month=12")
if assert_status(cal_summary_resp, 200, "10.4a: GET calendar summary after payment -> 200"):
    summary = cal_summary_resp.json()
    
    if "payments" in summary:
        payments_data = summary["payments"]
        
        # Should include our bill payment (225.0)
        if payments_data["amount"] >= 225.0:
            log_pass("10.4b: payments.amount includes bill payment")
        else:
            log_fail("10.4b: payments.amount", f"Expected >= 225.0, got {payments_data['amount']}")

print()

# ============================================================================
# TEST 11: REGRESSION (RECURRING PAYMENTS & DEBT PAYMENTS)
# ============================================================================
print("=" * 80)
print("TEST 11: REGRESSION")
print("=" * 80)

# 11.1: Create recurring payment (mode expense)
rp_resp = requests.post(f"{BASE_URL}/recurring-payments", json={
    "name": "Regression RP Test",
    "amount": 85.0,
    "category_id": test_category_id,
    "account_id": test_account_id,
    "frequency": "monthly",
    "start_date": "2026-11-01",
    "due_day": 1
})
if assert_status(rp_resp, 200, "11.1: Create recurring payment -> 200"):
    regression_rp_id = rp_resp.json()["id"]
    
    # 11.2: Pay recurring payment (mode expense)
    pay_resp = requests.post(f"{BASE_URL}/recurring-payments/{regression_rp_id}/payments", json={
        "due_date": "2026-11-01",
        "mode": "expense",
        "account_id": test_account_id,
        "date": "2026-11-01"
    })
    if assert_status(pay_resp, 200, "11.2: Pay recurring payment (expense) -> 200"):
        rp_payment_id = pay_resp.json()["id"]
        
        # 11.3: Delete recurring payment record
        delete_resp = requests.delete(f"{BASE_URL}/recurring-payments/payments/{rp_payment_id}")
        assert_status(delete_resp, 200, "11.3: Delete recurring payment record -> 200")

# 11.4: Create debt
debt_resp = requests.post(f"{BASE_URL}/debts", json={
    "name": "Regression Debt Test",
    "direction": "i_owe",
    "person": "Test Person",
    "original_amount": 500.0
})
if assert_status(debt_resp, 200, "11.4: Create debt -> 200"):
    regression_debt_id = debt_resp.json()["id"]
    
    # 11.5: Create debt payment
    debt_pay_resp = requests.post(f"{BASE_URL}/debt-payments", json={
        "debt_id": regression_debt_id,
        "amount": 200.0,
        "account_id": test_account_id,
        "date": "2026-10-11"
    })
    if assert_status(debt_pay_resp, 200, "11.5: Create debt payment -> 200"):
        debt_payment_id = debt_pay_resp.json()["id"]
        
        # 11.6: Delete debt payment
        delete_resp = requests.delete(f"{BASE_URL}/debt-payments/{debt_payment_id}")
        assert_status(delete_resp, 200, "11.6: Delete debt payment -> 200")

print()

# ============================================================================
# TEST 12: PUT /bills/{id} - CANNOT SET AMOUNT BELOW PAID
# ============================================================================
print("=" * 80)
print("TEST 12: PUT VALIDATION (AMOUNT < PAID)")
print("=" * 80)

# Create a bill and partially pay it
resp = requests.post(f"{BASE_URL}/bills", json={
    "name": "PUT Validation Test",
    "amount": 600.0,
    "due_date": "2026-12-20",
    "category_id": test_category_id,
    "account_id": test_account_id
})
put_test_bill_id = resp.json()["id"]

# Pay 400 out of 600
requests.post(f"{BASE_URL}/bills/{put_test_bill_id}/payments", json={
    "amount": 400.0,
    "account_id": test_account_id,
    "date": "2026-10-11"
})

# Try to update amount to 300 (< 400 paid) -> 422
resp = requests.put(f"{BASE_URL}/bills/{put_test_bill_id}", json={
    "name": "PUT Validation Test",
    "amount": 300.0,  # Less than paid amount (400)
    "due_date": "2026-12-20",
    "category_id": test_category_id,
    "account_id": test_account_id
})
assert_status(resp, 422, "12.1: PUT amount < paid -> 422")

# Update amount to 500 (> 400 paid) -> 200
resp = requests.put(f"{BASE_URL}/bills/{put_test_bill_id}", json={
    "name": "PUT Validation Test",
    "amount": 500.0,  # Greater than paid amount (400)
    "due_date": "2026-12-20",
    "category_id": test_category_id,
    "account_id": test_account_id
})
assert_status(resp, 200, "12.2: PUT amount > paid -> 200")

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print(f"Total tests: {tests_passed + tests_failed}")
print(f"✅ Passed: {tests_passed}")
print(f"❌ Failed: {tests_failed}")
print()

if tests_failed > 0:
    print("FAILURES:")
    for failure in failures:
        print(f"  ❌ {failure}")
    print()

# Calculate pass rate
pass_rate = (tests_passed / (tests_passed + tests_failed) * 100) if (tests_passed + tests_failed) > 0 else 0
print(f"Pass rate: {pass_rate:.1f}%")
print()

if tests_failed == 0:
    print("🎉 ALL TESTS PASSED!")
else:
    print(f"⚠️  {tests_failed} test(s) failed")

print("=" * 80)
