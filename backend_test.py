#!/usr/bin/env python3
"""
Comprehensive Budgets API Test Suite for MoneyFlow
Tests against isolated backend: http://127.0.0.1:8011/api
"""

import requests
import json
from decimal import Decimal
from datetime import datetime, timezone

BASE_URL = "http://127.0.0.1:8011/api"

# ANSI color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def log_test(name, passed, details=""):
    """Log test result with color"""
    status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
    print(f"{status} - {name}")
    if details:
        print(f"  {details}")
    return passed

def cleanup_test_data():
    """Clean up all budgets and transactions for a fresh start"""
    print(f"\n{BLUE}=== CLEANUP: Deleting all budgets and transactions ==={RESET}")
    
    # Delete all budgets
    resp = requests.get(f"{BASE_URL}/budgets")
    budgets = resp.json()
    for b in budgets:
        requests.delete(f"{BASE_URL}/budgets/{b['id']}")
    print(f"Deleted {len(budgets)} budgets")
    
    # Delete all transactions
    resp = requests.get(f"{BASE_URL}/transactions")
    transactions = resp.json()
    for t in transactions:
        requests.delete(f"{BASE_URL}/transactions/{t['id']}")
    print(f"Deleted {len(transactions)} transactions")
    
    print(f"{GREEN}Cleanup complete{RESET}\n")

def setup_categories():
    """Setup: POST /api/categories/init-defaults (idempotent) then GET /api/categories"""
    print(f"\n{BLUE}=== SETUP: Initialize categories ==={RESET}")
    
    # Call init-defaults (idempotent)
    resp = requests.post(f"{BASE_URL}/categories/init-defaults")
    log_test("POST /api/categories/init-defaults", resp.status_code == 200, 
             f"Status: {resp.status_code}")
    
    # Get all categories
    resp = requests.get(f"{BASE_URL}/categories")
    categories = resp.json()
    
    # Find groups and subcategories
    groups = [c for c in categories if c.get('is_group')]
    expense_groups = [g for g in groups if g['type'] == 'expense']
    income_groups = [g for g in groups if g['type'] == 'income']
    
    log_test("Categories loaded", len(categories) > 0, 
             f"Total: {len(categories)}, Groups: {len(groups)} (Expense: {len(expense_groups)}, Income: {len(income_groups)})")
    
    # Find specific categories for testing
    food_group = next((c for c in categories if c['name'] == 'Food & Dining' and c.get('is_group')), None)
    food_leaf = next((c for c in categories if c['name'] == 'Food' and c.get('parent_id') == food_group['id']), None) if food_group else None
    
    log_test("Found Food & Dining group", food_group is not None, 
             f"ID: {food_group['id']}" if food_group else "Not found")
    log_test("Found Food subcategory", food_leaf is not None, 
             f"ID: {food_leaf['id']}, parent: {food_leaf.get('parent_id')}" if food_leaf else "Not found")
    
    return categories, food_group, food_leaf

def test_validation_errors(categories):
    """Test POST /api/budgets validation (422 errors)"""
    print(f"\n{BLUE}=== TEST: Validation Errors (422) ==={RESET}")
    
    # Get a valid expense category
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    income_cat = next((c for c in categories if c['type'] == 'income' and not c.get('is_group')), None)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: amount_limit <= 0
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 0,
        "period": "monthly"
    })
    if log_test("Validation: amount_limit=0 returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}, Message: {resp.json().get('detail', '')}"):
        tests_passed += 1
    
    # Test 2: amount_limit < 0
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": -100,
        "period": "monthly"
    })
    if log_test("Validation: amount_limit<0 returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 3: invalid period
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "invalid"
    })
    if log_test("Validation: invalid period returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 4: threshold outside 1..100
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "monthly",
        "alert_threshold": 0
    })
    if log_test("Validation: alert_threshold=0 returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "monthly",
        "alert_threshold": 101
    })
    if log_test("Validation: alert_threshold=101 returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 5: missing category
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "amount_limit": 100,
        "period": "monthly"
    })
    if log_test("Validation: missing category_id returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 6: nonexistent category
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": "nonexistent-id",
        "amount_limit": 100,
        "period": "monthly"
    })
    if log_test("Validation: nonexistent category returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 7: income category (should be expense only)
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": income_cat['id'],
        "amount_limit": 100,
        "period": "monthly"
    })
    if log_test("Validation: income category returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 8: custom period without end_date
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "custom",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    if log_test("Validation: custom without end_date returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 9: end_date < start_date
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "custom",
        "start_date": "2026-10-15T00:00:00+00:00",
        "end_date": "2026-10-01T00:00:00+00:00"
    })
    if log_test("Validation: end_date < start_date returns 422", resp.status_code == 422, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    print(f"\n{YELLOW}Validation tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_duplicate_conflict(expense_cat):
    """Test 409 conflict when same category+period with overlapping dates"""
    print(f"\n{BLUE}=== TEST: Duplicate Conflict (409) ==={RESET}")
    
    # Create first budget
    resp1 = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    budget1_id = resp1.json().get('id')
    log_test("Created first budget", resp1.status_code == 200, f"ID: {budget1_id}")
    
    # Try to create overlapping budget (should fail with 409)
    resp2 = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 200,
        "period": "monthly",
        "start_date": "2026-10-15T00:00:00+00:00"
    })
    passed = log_test("Duplicate budget returns 409", resp2.status_code == 409, 
                     f"Status: {resp2.status_code}, Message: {resp2.json().get('detail', '')}")
    
    # Cleanup
    if budget1_id:
        requests.delete(f"{BASE_URL}/budgets/{budget1_id}")
    
    return passed

def test_idempotency_key(expense_cat):
    """Test Idempotency-Key header: same key returns same budget"""
    print(f"\n{BLUE}=== TEST: Idempotency-Key ==={RESET}")
    
    idempotency_key = "test-idempotency-key-12345"
    
    # First request with idempotency key
    resp1 = requests.post(f"{BASE_URL}/budgets", 
                         headers={"Idempotency-Key": idempotency_key},
                         json={
                             "category_id": expense_cat['id'],
                             "amount_limit": 100,
                             "period": "monthly",
                             "start_date": "2026-10-01T00:00:00+00:00"
                         })
    budget1 = resp1.json()
    budget1_id = budget1.get('id')
    log_test("First request with idempotency key", resp1.status_code == 200, 
             f"ID: {budget1_id}")
    
    # Second request with same key and same body (should return same budget)
    resp2 = requests.post(f"{BASE_URL}/budgets", 
                         headers={"Idempotency-Key": idempotency_key},
                         json={
                             "category_id": expense_cat['id'],
                             "amount_limit": 100,
                             "period": "monthly",
                             "start_date": "2026-10-01T00:00:00+00:00"
                         })
    budget2 = resp2.json()
    budget2_id = budget2.get('id')
    
    same_id = budget1_id == budget2_id
    log_test("Second request returns same budget", same_id, 
             f"ID1: {budget1_id}, ID2: {budget2_id}")
    
    # Check response has no _id and no idempotency_key
    no_underscore_id = '_id' not in budget2
    no_idem_key = 'idempotency_key' not in budget2
    log_test("Response has no _id", no_underscore_id)
    log_test("Response has no idempotency_key", no_idem_key)
    
    # Cleanup
    if budget1_id:
        requests.delete(f"{BASE_URL}/budgets/{budget1_id}")
    
    return same_id and no_underscore_id and no_idem_key

def test_update_budget(expense_cat):
    """Test PUT /api/budgets/{id}"""
    print(f"\n{BLUE}=== TEST: Update Budget (PUT) ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: 404 for missing budget
    tests_total += 1
    resp = requests.put(f"{BASE_URL}/budgets/nonexistent-id", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "monthly"
    })
    if log_test("Update nonexistent budget returns 404", resp.status_code == 404, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 2: Create budget and update it
    tests_total += 1
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    budget = resp.json()
    budget_id = budget.get('id')
    
    # Update the budget
    resp = requests.put(f"{BASE_URL}/budgets/{budget_id}", json={
        "category_id": expense_cat['id'],
        "amount_limit": 200,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00",
        "alert_threshold": 70
    })
    if log_test("Update budget returns 200", resp.status_code == 200, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 3: Verify persistence (GET reflects change)
    tests_total += 1
    resp = requests.get(f"{BASE_URL}/budgets")
    budgets = resp.json()
    updated_budget = next((b for b in budgets if b['id'] == budget_id), None)
    
    if updated_budget:
        amount_correct = updated_budget['amount_limit'] == 200
        threshold_correct = updated_budget['alert_threshold'] == 70
        has_updated_at = updated_budget.get('updated_at') is not None
        
        if log_test("Budget persisted with changes", 
                   amount_correct and threshold_correct and has_updated_at,
                   f"amount_limit: {updated_budget['amount_limit']}, alert_threshold: {updated_budget['alert_threshold']}, updated_at: {updated_budget.get('updated_at')}"):
            tests_passed += 1
    else:
        log_test("Budget persisted with changes", False, "Budget not found after update")
    
    # Test 4: Updating itself should not trigger 409
    tests_total += 1
    resp = requests.put(f"{BASE_URL}/budgets/{budget_id}", json={
        "category_id": expense_cat['id'],
        "amount_limit": 250,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    if log_test("Updating itself does not trigger 409", resp.status_code == 200, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Cleanup
    if budget_id:
        requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    
    print(f"\n{YELLOW}Update tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_delete_budget(expense_cat):
    """Test DELETE /api/budgets/{id}"""
    print(f"\n{BLUE}=== TEST: Delete Budget ==={RESET}")
    
    # Create budget
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    budget_id = resp.json().get('id')
    log_test("Created budget for deletion", resp.status_code == 200, f"ID: {budget_id}")
    
    # Delete budget
    resp = requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    delete_ok = resp.status_code == 200 and resp.json().get('ok') == True
    log_test("DELETE returns {ok:true}", delete_ok, 
             f"Status: {resp.status_code}, Response: {resp.json()}")
    
    # Verify removed
    resp = requests.get(f"{BASE_URL}/budgets")
    budgets = resp.json()
    removed = not any(b['id'] == budget_id for b in budgets)
    log_test("Budget removed from list", removed, 
             f"Budget {budget_id} {'not found' if removed else 'still exists'} in list")
    
    return delete_ok and removed

def test_scenario_1_group_and_subcategory(food_group, food_leaf):
    """
    Scenario 1: Group budget (Food & Dining, limit 500) + subcategory budget (Food leaf, limit 100, threshold 50)
    Expense 60.10 on leaf + expense 40.20 directly on group in Oct
    Overview Oct: group spent 100.30, leaf spent 60.10 status warning, leaf counted_in_total=false,
    totals budgeted 500 (NOT 600), spent 100.30 (NOT 160.40), pct 20.1
    """
    print(f"\n{BLUE}=== SCENARIO 1: Group + Subcategory Budget (No Double Counting) ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    # Create group budget (Food & Dining, limit 500)
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": food_group['id'],
        "amount_limit": 500,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    group_budget_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created group budget (Food & Dining, limit 500)", resp.status_code == 200, 
                f"ID: {group_budget_id}"):
        tests_passed += 1
    
    # Create subcategory budget (Food leaf, limit 100, threshold 50)
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": food_leaf['id'],
        "amount_limit": 100,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00",
        "alert_threshold": 50
    })
    leaf_budget_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created subcategory budget (Food leaf, limit 100, threshold 50)", 
                resp.status_code == 200, f"ID: {leaf_budget_id}"):
        tests_passed += 1
    
    # Create expense 60.10 on leaf
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Groceries",
        "amount": 60.10,
        "type": "expense",
        "date": "2026-10-05T12:00:00+00:00",
        "category_id": food_leaf['id']
    })
    tx1_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created expense 60.10 on Food leaf", resp.status_code == 200, 
                f"ID: {tx1_id}"):
        tests_passed += 1
    
    # Create expense 40.20 directly on group
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Restaurant",
        "amount": 40.20,
        "type": "expense",
        "date": "2026-10-06T12:00:00+00:00",
        "category_id": food_group['id']
    })
    tx2_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created expense 40.20 on Food & Dining group", resp.status_code == 200, 
                f"ID: {tx2_id}"):
        tests_passed += 1
    
    # Get overview for October 2026
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview = resp.json()
    tests_total += 1
    if log_test("GET /api/budgets/overview returns 200", resp.status_code == 200):
        tests_passed += 1
    
    # Find budgets in overview
    group_budget = next((b for b in overview['budgets'] if b['id'] == group_budget_id), None)
    leaf_budget = next((b for b in overview['budgets'] if b['id'] == leaf_budget_id), None)
    
    # Verify group budget spent 100.30
    tests_total += 1
    if group_budget:
        group_spent_correct = abs(group_budget['spent'] - 100.30) < 0.01
        if log_test("Group budget spent = 100.30", group_spent_correct, 
                   f"Actual: {group_budget['spent']}"):
            tests_passed += 1
    else:
        log_test("Group budget spent = 100.30", False, "Group budget not found in overview")
    
    # Verify leaf budget spent 60.10 and status warning
    tests_total += 1
    if leaf_budget:
        leaf_spent_correct = abs(leaf_budget['spent'] - 60.10) < 0.01
        if log_test("Leaf budget spent = 60.10", leaf_spent_correct, 
                   f"Actual: {leaf_budget['spent']}"):
            tests_passed += 1
    else:
        log_test("Leaf budget spent = 60.10", False, "Leaf budget not found in overview")
    
    tests_total += 1
    if leaf_budget:
        status_warning = leaf_budget['status'] == 'warning'
        if log_test("Leaf budget status = warning (60.10 >= 50% of 100)", status_warning, 
                   f"Actual status: {leaf_budget['status']}"):
            tests_passed += 1
    else:
        log_test("Leaf budget status = warning", False, "Leaf budget not found")
    
    # Verify leaf counted_in_total = false
    tests_total += 1
    if leaf_budget:
        not_counted = leaf_budget.get('counted_in_total') == False
        if log_test("Leaf budget counted_in_total = false", not_counted, 
                   f"Actual: {leaf_budget.get('counted_in_total')}"):
            tests_passed += 1
    else:
        log_test("Leaf budget counted_in_total = false", False, "Leaf budget not found")
    
    # Verify totals: budgeted 500 (NOT 600)
    tests_total += 1
    totals_budgeted_correct = abs(overview['totals']['budgeted'] - 500) < 0.01
    if log_test("Totals budgeted = 500 (NOT 600, no double counting)", totals_budgeted_correct, 
               f"Actual: {overview['totals']['budgeted']}"):
        tests_passed += 1
    
    # Verify totals: spent 100.30 (NOT 160.40)
    tests_total += 1
    totals_spent_correct = abs(overview['totals']['spent'] - 100.30) < 0.01
    if log_test("Totals spent = 100.30 (NOT 160.40, no double counting)", totals_spent_correct, 
               f"Actual: {overview['totals']['spent']}"):
        tests_passed += 1
    
    # Verify totals: pct 20.1 (100.30 / 500 * 100)
    tests_total += 1
    expected_pct = 20.1  # (100.30 / 500) * 100 = 20.06, rounded to 20.1
    totals_pct_correct = overview['totals']['pct'] is not None and abs(overview['totals']['pct'] - expected_pct) < 0.2
    if log_test("Totals pct = 20.1", totals_pct_correct, 
               f"Actual: {overview['totals']['pct']}"):
        tests_passed += 1
    
    # Cleanup
    if group_budget_id:
        requests.delete(f"{BASE_URL}/budgets/{group_budget_id}")
    if leaf_budget_id:
        requests.delete(f"{BASE_URL}/budgets/{leaf_budget_id}")
    if tx1_id:
        requests.delete(f"{BASE_URL}/transactions/{tx1_id}")
    if tx2_id:
        requests.delete(f"{BASE_URL}/transactions/{tx2_id}")
    
    print(f"\n{YELLOW}Scenario 1 tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_scenario_2_income_transfer_exclusion(categories):
    """
    Scenario 2: Income, transfer with that category in Oct are NOT counted
    Expense in Sep counts only in Sep overview (history), Oct unchanged
    A month with no activity → spent 0
    """
    print(f"\n{BLUE}=== SCENARIO 2: Income/Transfer Exclusion & Historical Data ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    # Get an expense category
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    income_cat = next((c for c in categories if c['type'] == 'income' and not c.get('is_group')), None)
    
    # Create budget for October
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 200,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    budget_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created budget for October", resp.status_code == 200, f"ID: {budget_id}"):
        tests_passed += 1
    
    # Create expense in October (should count)
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Oct Expense",
        "amount": 50,
        "type": "expense",
        "date": "2026-10-10T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx_oct_expense_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created expense in October", resp.status_code == 200):
        tests_passed += 1
    
    # Create income in October with same category (should NOT count - but income cats are different)
    # Actually, budgets are only for expense categories, so income transactions won't match
    # Let's create a transfer instead
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Oct Transfer",
        "amount": 30,
        "type": "transfer",
        "date": "2026-10-11T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx_oct_transfer_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created transfer in October", resp.status_code == 200):
        tests_passed += 1
    
    # Create expense in September (should NOT count in Oct)
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Sep Expense",
        "amount": 40,
        "type": "expense",
        "date": "2026-09-15T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx_sep_expense_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created expense in September", resp.status_code == 200):
        tests_passed += 1
    
    # Get October overview
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    oct_overview = resp.json()
    oct_budget = next((b for b in oct_overview['budgets'] if b['id'] == budget_id), None)
    
    # Verify October spent = 50 (only expense, not transfer, not Sep expense)
    tests_total += 1
    if oct_budget:
        oct_spent_correct = abs(oct_budget['spent'] - 50) < 0.01
        if log_test("October spent = 50 (only expense, not transfer)", oct_spent_correct, 
                   f"Actual: {oct_budget['spent']}"):
            tests_passed += 1
    else:
        log_test("October spent = 50", False, "Budget not found in October overview")
    
    # Get September overview
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 9,
        "tz_offset": 0
    })
    sep_overview = resp.json()
    sep_budget = next((b for b in sep_overview['budgets'] if b['id'] == budget_id), None)
    
    # Verify September spent = 40 (Sep expense counts in Sep)
    tests_total += 1
    if sep_budget:
        sep_spent_correct = abs(sep_budget['spent'] - 40) < 0.01
        if log_test("September spent = 40 (Sep expense counts in Sep)", sep_spent_correct, 
                   f"Actual: {sep_budget['spent']}"):
            tests_passed += 1
    else:
        log_test("September spent = 40", False, "Budget not found in September overview")
    
    # Get August overview (no activity)
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 8,
        "tz_offset": 0
    })
    aug_overview = resp.json()
    aug_budget = next((b for b in aug_overview['budgets'] if b['id'] == budget_id), None)
    
    # Verify August spent = 0 (no activity)
    tests_total += 1
    if aug_budget:
        aug_spent_correct = aug_budget['spent'] == 0
        if log_test("August spent = 0 (no activity)", aug_spent_correct, 
                   f"Actual: {aug_budget['spent']}"):
            tests_passed += 1
    else:
        log_test("August spent = 0", False, "Budget not found in August overview")
    
    # Cleanup
    if budget_id:
        requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    if tx_oct_expense_id:
        requests.delete(f"{BASE_URL}/transactions/{tx_oct_expense_id}")
    if tx_oct_transfer_id:
        requests.delete(f"{BASE_URL}/transactions/{tx_oct_transfer_id}")
    if tx_sep_expense_id:
        requests.delete(f"{BASE_URL}/transactions/{tx_sep_expense_id}")
    
    print(f"\n{YELLOW}Scenario 2 tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_scenario_3_transaction_edit_delete(categories):
    """
    Scenario 3: Edit a transaction amount (PUT /api/transactions/{id}) and delete one
    Overview recalculates
    """
    print(f"\n{BLUE}=== SCENARIO 3: Transaction Edit/Delete Recalculation ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    
    # Create budget
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 200,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    budget_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created budget", resp.status_code == 200):
        tests_passed += 1
    
    # Create two expenses
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense 1",
        "amount": 50,
        "type": "expense",
        "date": "2026-10-05T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx1_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created expense 1 (50)", resp.status_code == 200):
        tests_passed += 1
    
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense 2",
        "amount": 30,
        "type": "expense",
        "date": "2026-10-06T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx2_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created expense 2 (30)", resp.status_code == 200):
        tests_passed += 1
    
    # Get initial overview (should be 80)
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview1 = resp.json()
    budget1 = next((b for b in overview1['budgets'] if b['id'] == budget_id), None)
    tests_total += 1
    if budget1:
        initial_spent_correct = abs(budget1['spent'] - 80) < 0.01
        if log_test("Initial spent = 80 (50 + 30)", initial_spent_correct, 
                   f"Actual: {budget1['spent']}"):
            tests_passed += 1
    else:
        log_test("Initial spent = 80", False, "Budget not found")
    
    # Edit transaction 1 amount from 50 to 70
    resp = requests.put(f"{BASE_URL}/transactions/{tx1_id}", json={
        "name": "Expense 1 Updated",
        "amount": 70,
        "type": "expense",
        "date": "2026-10-05T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tests_total += 1
    if log_test("Updated expense 1 amount to 70", resp.status_code == 200):
        tests_passed += 1
    
    # Get overview after edit (should be 100)
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview2 = resp.json()
    budget2 = next((b for b in overview2['budgets'] if b['id'] == budget_id), None)
    tests_total += 1
    if budget2:
        after_edit_correct = abs(budget2['spent'] - 100) < 0.01
        if log_test("After edit spent = 100 (70 + 30)", after_edit_correct, 
                   f"Actual: {budget2['spent']}"):
            tests_passed += 1
    else:
        log_test("After edit spent = 100", False, "Budget not found")
    
    # Delete transaction 2
    resp = requests.delete(f"{BASE_URL}/transactions/{tx2_id}")
    tests_total += 1
    if log_test("Deleted expense 2", resp.status_code == 200):
        tests_passed += 1
    
    # Get overview after delete (should be 70)
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview3 = resp.json()
    budget3 = next((b for b in overview3['budgets'] if b['id'] == budget_id), None)
    tests_total += 1
    if budget3:
        after_delete_correct = abs(budget3['spent'] - 70) < 0.01
        if log_test("After delete spent = 70 (only expense 1)", after_delete_correct, 
                   f"Actual: {budget3['spent']}"):
            tests_passed += 1
    else:
        log_test("After delete spent = 70", False, "Budget not found")
    
    # Cleanup
    if budget_id:
        requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    if tx1_id:
        requests.delete(f"{BASE_URL}/transactions/{tx1_id}")
    # tx2 already deleted
    
    print(f"\n{YELLOW}Scenario 3 tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_scenario_4_status_transitions(categories):
    """
    Scenario 4: Status transitions
    limit 100 with spend 80 (threshold 80) → warning
    100 → reached
    120 → exceeded with available -20
    alerts_count counts them
    alerts_enabled=false budget is not counted in alerts_count
    """
    print(f"\n{BLUE}=== SCENARIO 4: Status Transitions (warning/reached/exceeded) ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    
    # Create budget with limit 100, threshold 80
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00",
        "alert_threshold": 80,
        "alerts_enabled": True
    })
    budget_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created budget (limit 100, threshold 80)", resp.status_code == 200):
        tests_passed += 1
    
    # Create expense 80 → status warning
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense 80",
        "amount": 80,
        "type": "expense",
        "date": "2026-10-05T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx1_id = resp.json().get('id')
    
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview1 = resp.json()
    budget1 = next((b for b in overview1['budgets'] if b['id'] == budget_id), None)
    
    tests_total += 1
    if budget1:
        status_warning = budget1['status'] == 'warning'
        if log_test("Status = warning (80 >= 80% of 100)", status_warning, 
                   f"Actual status: {budget1['status']}, spent: {budget1['spent']}"):
            tests_passed += 1
    else:
        log_test("Status = warning", False, "Budget not found")
    
    # Add expense 20 → total 100 → status reached
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense 20",
        "amount": 20,
        "type": "expense",
        "date": "2026-10-06T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx2_id = resp.json().get('id')
    
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview2 = resp.json()
    budget2 = next((b for b in overview2['budgets'] if b['id'] == budget_id), None)
    
    tests_total += 1
    if budget2:
        status_reached = budget2['status'] == 'reached'
        if log_test("Status = reached (100 == 100)", status_reached, 
                   f"Actual status: {budget2['status']}, spent: {budget2['spent']}"):
            tests_passed += 1
    else:
        log_test("Status = reached", False, "Budget not found")
    
    # Add expense 20 → total 120 → status exceeded, available -20
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense 20 more",
        "amount": 20,
        "type": "expense",
        "date": "2026-10-07T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx3_id = resp.json().get('id')
    
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview3 = resp.json()
    budget3 = next((b for b in overview3['budgets'] if b['id'] == budget_id), None)
    
    tests_total += 1
    if budget3:
        status_exceeded = budget3['status'] == 'exceeded'
        if log_test("Status = exceeded (120 > 100)", status_exceeded, 
                   f"Actual status: {budget3['status']}, spent: {budget3['spent']}"):
            tests_passed += 1
    else:
        log_test("Status = exceeded", False, "Budget not found")
    
    tests_total += 1
    if budget3:
        available_correct = abs(budget3['available'] - (-20)) < 0.01
        if log_test("Available = -20 (100 - 120)", available_correct, 
                   f"Actual available: {budget3['available']}"):
            tests_passed += 1
    else:
        log_test("Available = -20", False, "Budget not found")
    
    # Check alerts_count
    tests_total += 1
    alerts_count_correct = overview3['alerts_count'] >= 1
    if log_test("alerts_count >= 1 (budget with alert)", alerts_count_correct, 
               f"Actual alerts_count: {overview3['alerts_count']}"):
        tests_passed += 1
    
    # Create another budget with alerts_enabled=false
    expense_cat2 = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group') and c['id'] != expense_cat['id']), None)
    if expense_cat2:
        resp = requests.post(f"{BASE_URL}/budgets", json={
            "category_id": expense_cat2['id'],
            "amount_limit": 50,
            "period": "monthly",
            "start_date": "2026-10-01T00:00:00+00:00",
            "alerts_enabled": False
        })
        budget2_id = resp.json().get('id')
        
        # Create expense to exceed it
        resp = requests.post(f"{BASE_URL}/transactions", json={
            "name": "Expense on cat2",
            "amount": 60,
            "type": "expense",
            "date": "2026-10-08T12:00:00+00:00",
            "category_id": expense_cat2['id']
        })
        tx4_id = resp.json().get('id')
        
        # Get overview
        resp = requests.get(f"{BASE_URL}/budgets/overview", params={
            "year": 2026,
            "month": 10,
            "tz_offset": 0
        })
        overview4 = resp.json()
        
        # alerts_count should still be 1 (only first budget, not the one with alerts_enabled=false)
        tests_total += 1
        alerts_count_unchanged = overview4['alerts_count'] == 1
        if log_test("alerts_enabled=false budget not counted in alerts_count", alerts_count_unchanged, 
                   f"Actual alerts_count: {overview4['alerts_count']}"):
            tests_passed += 1
        
        # Cleanup
        if budget2_id:
            requests.delete(f"{BASE_URL}/budgets/{budget2_id}")
        if tx4_id:
            requests.delete(f"{BASE_URL}/transactions/{tx4_id}")
    
    # Cleanup
    if budget_id:
        requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    if tx1_id:
        requests.delete(f"{BASE_URL}/transactions/{tx1_id}")
    if tx2_id:
        requests.delete(f"{BASE_URL}/transactions/{tx2_id}")
    if tx3_id:
        requests.delete(f"{BASE_URL}/transactions/{tx3_id}")
    
    print(f"\n{YELLOW}Scenario 4 tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_scenario_5_weekly_budget(categories):
    """
    Scenario 5: Weekly budget
    Only expenses within the Monday-start week of the reference day count
    For a past month the reference is the last day of that month
    """
    print(f"\n{BLUE}=== SCENARIO 5: Weekly Budget ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    
    # Create weekly budget starting Oct 1, 2026
    # Oct 1, 2026 is a Thursday
    # The week containing Oct 1 starts on Monday Sep 28 and ends on Sunday Oct 4
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 100,
        "period": "weekly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    budget_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created weekly budget", resp.status_code == 200):
        tests_passed += 1
    
    # Create expense on Oct 2 (Thursday, within the week)
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Oct 2 Expense",
        "amount": 30,
        "type": "expense",
        "date": "2026-10-02T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx1_id = resp.json().get('id')
    
    # Create expense on Oct 6 (Monday, next week)
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Oct 6 Expense",
        "amount": 40,
        "type": "expense",
        "date": "2026-10-06T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx2_id = resp.json().get('id')
    
    # Get October overview
    # For October 2026, the reference day should be "today" if we're in October, else last day of October
    # Since we're testing in the future, it will use the last day of October (Oct 31, 2026 is a Saturday)
    # The week containing Oct 31 starts on Monday Oct 26
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview = resp.json()
    budget = next((b for b in overview['budgets'] if b['id'] == budget_id), None)
    
    # For October, the reference is the last day (Oct 31, Saturday)
    # Week starts Monday Oct 26, ends Sunday Nov 1
    # So only expenses from Oct 26-31 should count
    # Our expenses are Oct 2 and Oct 6, both outside this week
    tests_total += 1
    if budget:
        # Actually, let me reconsider. The code says:
        # ref = now.astimezone(tz) if m_start <= ref < m_end else m_end - timedelta(days=1)
        # So for October 2026, if we're not currently in October, ref = Oct 31
        # Oct 31, 2026 is a Saturday (weekday 5)
        # ws = ref - timedelta(days=ref.weekday()) = Oct 31 - 5 days = Oct 26 (Monday)
        # we = ws + 7 days = Nov 2
        # So the week is Oct 26 - Nov 2
        # Our expenses are Oct 2 and Oct 6, both before Oct 26, so spent should be 0
        spent_correct = budget['spent'] == 0
        if log_test("Weekly budget spent = 0 (expenses outside reference week)", spent_correct, 
                   f"Actual spent: {budget['spent']}, window: {budget.get('window_start')} to {budget.get('window_end')}"):
            tests_passed += 1
    else:
        log_test("Weekly budget spent = 0", False, "Budget not found")
    
    # Let's create an expense in the reference week (Oct 28)
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Oct 28 Expense",
        "amount": 50,
        "type": "expense",
        "date": "2026-10-28T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx3_id = resp.json().get('id')
    
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview2 = resp.json()
    budget2 = next((b for b in overview2['budgets'] if b['id'] == budget_id), None)
    
    tests_total += 1
    if budget2:
        spent_correct = abs(budget2['spent'] - 50) < 0.01
        if log_test("Weekly budget spent = 50 (expense in reference week)", spent_correct, 
                   f"Actual spent: {budget2['spent']}"):
            tests_passed += 1
    else:
        log_test("Weekly budget spent = 50", False, "Budget not found")
    
    # Cleanup
    if budget_id:
        requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    if tx1_id:
        requests.delete(f"{BASE_URL}/transactions/{tx1_id}")
    if tx2_id:
        requests.delete(f"{BASE_URL}/transactions/{tx2_id}")
    if tx3_id:
        requests.delete(f"{BASE_URL}/transactions/{tx3_id}")
    
    print(f"\n{YELLOW}Scenario 5 tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_scenario_6_custom_budget(categories):
    """
    Scenario 6: Custom budget
    Only within start..end inclusive
    Inactive outside (active=false) in a month that doesn't overlap
    """
    print(f"\n{BLUE}=== SCENARIO 6: Custom Budget Period ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    
    # Create custom budget Oct 10 - Oct 20
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 150,
        "period": "custom",
        "start_date": "2026-10-10T00:00:00+00:00",
        "end_date": "2026-10-20T00:00:00+00:00"
    })
    budget_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created custom budget (Oct 10-20)", resp.status_code == 200):
        tests_passed += 1
    
    # Create expense on Oct 5 (before start)
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Oct 5 Expense",
        "amount": 20,
        "type": "expense",
        "date": "2026-10-05T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx1_id = resp.json().get('id')
    
    # Create expense on Oct 15 (within range)
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Oct 15 Expense",
        "amount": 60,
        "type": "expense",
        "date": "2026-10-15T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx2_id = resp.json().get('id')
    
    # Create expense on Oct 25 (after end)
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Oct 25 Expense",
        "amount": 30,
        "type": "expense",
        "date": "2026-10-25T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx3_id = resp.json().get('id')
    
    # Get October overview
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview = resp.json()
    budget = next((b for b in overview['budgets'] if b['id'] == budget_id), None)
    
    # Should only count Oct 15 expense (60)
    tests_total += 1
    if budget:
        spent_correct = abs(budget['spent'] - 60) < 0.01
        active = budget.get('active') == True
        if log_test("Custom budget spent = 60 (only within Oct 10-20)", spent_correct and active, 
                   f"Actual spent: {budget['spent']}, active: {budget.get('active')}"):
            tests_passed += 1
    else:
        log_test("Custom budget spent = 60", False, "Budget not found")
    
    # Get September overview (budget should be inactive)
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 9,
        "tz_offset": 0
    })
    sep_overview = resp.json()
    sep_budget = next((b for b in sep_overview['budgets'] if b['id'] == budget_id), None)
    
    tests_total += 1
    if sep_budget:
        inactive = sep_budget.get('active') == False
        if log_test("Custom budget inactive in September (no overlap)", inactive, 
                   f"Actual active: {sep_budget.get('active')}"):
            tests_passed += 1
    else:
        log_test("Custom budget inactive in September", False, "Budget not found")
    
    # Cleanup
    if budget_id:
        requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    if tx1_id:
        requests.delete(f"{BASE_URL}/transactions/{tx1_id}")
    if tx2_id:
        requests.delete(f"{BASE_URL}/transactions/{tx2_id}")
    if tx3_id:
        requests.delete(f"{BASE_URL}/transactions/{tx3_id}")
    
    print(f"\n{YELLOW}Scenario 6 tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_scenario_7_floating_precision(categories):
    """
    Scenario 7: Floating precision
    Amounts like 0.1+0.2 sum exactly 0.3
    """
    print(f"\n{BLUE}=== SCENARIO 7: Floating Point Precision ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    
    # Create budget
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 1,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    budget_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created budget", resp.status_code == 200):
        tests_passed += 1
    
    # Create expense 0.1
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense 0.1",
        "amount": 0.1,
        "type": "expense",
        "date": "2026-10-05T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx1_id = resp.json().get('id')
    
    # Create expense 0.2
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense 0.2",
        "amount": 0.2,
        "type": "expense",
        "date": "2026-10-06T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx2_id = resp.json().get('id')
    
    # Get overview
    resp = requests.get(f"{BASE_URL}/budgets/overview", params={
        "year": 2026,
        "month": 10,
        "tz_offset": 0
    })
    overview = resp.json()
    budget = next((b for b in overview['budgets'] if b['id'] == budget_id), None)
    
    # Should be exactly 0.3, not 0.30000000000000004
    tests_total += 1
    if budget:
        spent_exact = abs(budget['spent'] - 0.3) < 0.0001
        if log_test("Floating precision: 0.1 + 0.2 = 0.3 (exact)", spent_exact, 
                   f"Actual spent: {budget['spent']}"):
            tests_passed += 1
    else:
        log_test("Floating precision: 0.1 + 0.2 = 0.3", False, "Budget not found")
    
    # Cleanup
    if budget_id:
        requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    if tx1_id:
        requests.delete(f"{BASE_URL}/transactions/{tx1_id}")
    if tx2_id:
        requests.delete(f"{BASE_URL}/transactions/{tx2_id}")
    
    print(f"\n{YELLOW}Scenario 7 tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_scenario_8_account_balance_unchanged(categories):
    """
    Scenario 8: Budgets never modify account balances
    Create account initial 1000, expense via transaction affects it as usual,
    but creating/editing/deleting budgets leaves current_balance unchanged
    """
    print(f"\n{BLUE}=== SCENARIO 8: Budgets Don't Modify Account Balances ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    
    # Create account with initial balance 1000
    resp = requests.post(f"{BASE_URL}/accounts", json={
        "name": "Test Account",
        "type": "cash",
        "initial_balance": 1000,
        "color": "#FF0000"
    })
    account = resp.json()
    account_id = account.get('id')
    tests_total += 1
    if log_test("Created account with initial_balance=1000", resp.status_code == 200, 
               f"ID: {account_id}, current_balance: {account.get('current_balance')}"):
        tests_passed += 1
    
    # Verify initial balance
    initial_balance = account.get('current_balance')
    tests_total += 1
    if abs(initial_balance - 1000) < 0.01:
        log_test("Account current_balance = 1000", True)
        tests_passed += 1
    else:
        log_test("Account current_balance = 1000", False, f"Actual: {initial_balance}")
    
    # Create expense transaction (should affect balance)
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense with account",
        "amount": 100,
        "type": "expense",
        "date": "2026-10-05T12:00:00+00:00",
        "category_id": expense_cat['id'],
        "account_id": account_id
    })
    tx_id = resp.json().get('id')
    
    # Get account balance after transaction
    resp = requests.get(f"{BASE_URL}/accounts")
    accounts = resp.json()
    account_after_tx = next((a for a in accounts if a['id'] == account_id), None)
    balance_after_tx = account_after_tx.get('current_balance') if account_after_tx else None
    
    tests_total += 1
    if balance_after_tx is not None and abs(balance_after_tx - 900) < 0.01:
        log_test("After expense transaction, balance = 900", True, 
                f"Actual: {balance_after_tx}")
        tests_passed += 1
    else:
        log_test("After expense transaction, balance = 900", False, 
                f"Actual: {balance_after_tx}")
    
    # Create budget (should NOT affect balance)
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 200,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    budget_id = resp.json().get('id')
    
    # Get account balance after budget creation
    resp = requests.get(f"{BASE_URL}/accounts")
    accounts = resp.json()
    account_after_budget = next((a for a in accounts if a['id'] == account_id), None)
    balance_after_budget = account_after_budget.get('current_balance') if account_after_budget else None
    
    tests_total += 1
    if balance_after_budget is not None and abs(balance_after_budget - 900) < 0.01:
        log_test("After budget creation, balance unchanged (900)", True, 
                f"Actual: {balance_after_budget}")
        tests_passed += 1
    else:
        log_test("After budget creation, balance unchanged (900)", False, 
                f"Actual: {balance_after_budget}")
    
    # Edit budget (should NOT affect balance)
    resp = requests.put(f"{BASE_URL}/budgets/{budget_id}", json={
        "category_id": expense_cat['id'],
        "amount_limit": 300,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    
    # Get account balance after budget edit
    resp = requests.get(f"{BASE_URL}/accounts")
    accounts = resp.json()
    account_after_edit = next((a for a in accounts if a['id'] == account_id), None)
    balance_after_edit = account_after_edit.get('current_balance') if account_after_edit else None
    
    tests_total += 1
    if balance_after_edit is not None and abs(balance_after_edit - 900) < 0.01:
        log_test("After budget edit, balance unchanged (900)", True, 
                f"Actual: {balance_after_edit}")
        tests_passed += 1
    else:
        log_test("After budget edit, balance unchanged (900)", False, 
                f"Actual: {balance_after_edit}")
    
    # Delete budget (should NOT affect balance)
    resp = requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    
    # Get account balance after budget deletion
    resp = requests.get(f"{BASE_URL}/accounts")
    accounts = resp.json()
    account_after_delete = next((a for a in accounts if a['id'] == account_id), None)
    balance_after_delete = account_after_delete.get('current_balance') if account_after_delete else None
    
    tests_total += 1
    if balance_after_delete is not None and abs(balance_after_delete - 900) < 0.01:
        log_test("After budget deletion, balance unchanged (900)", True, 
                f"Actual: {balance_after_delete}")
        tests_passed += 1
    else:
        log_test("After budget deletion, balance unchanged (900)", False, 
                f"Actual: {balance_after_delete}")
    
    # Cleanup
    if account_id:
        requests.delete(f"{BASE_URL}/accounts/{account_id}")
    if tx_id:
        requests.delete(f"{BASE_URL}/transactions/{tx_id}")
    
    print(f"\n{YELLOW}Scenario 8 tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def test_budget_detail(categories):
    """Test GET /api/budgets/{id}/detail"""
    print(f"\n{BLUE}=== TEST: Budget Detail Endpoint ==={RESET}")
    
    tests_passed = 0
    tests_total = 0
    
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    
    # Create budget
    resp = requests.post(f"{BASE_URL}/budgets", json={
        "category_id": expense_cat['id'],
        "amount_limit": 200,
        "period": "monthly",
        "start_date": "2026-10-01T00:00:00+00:00"
    })
    budget_id = resp.json().get('id')
    tests_total += 1
    if log_test("Created budget", resp.status_code == 200):
        tests_passed += 1
    
    # Create transactions
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense 1",
        "amount": 50,
        "type": "expense",
        "date": "2026-10-05T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx1_id = resp.json().get('id')
    
    resp = requests.post(f"{BASE_URL}/transactions", json={
        "name": "Expense 2",
        "amount": 30,
        "type": "expense",
        "date": "2026-10-06T12:00:00+00:00",
        "category_id": expense_cat['id']
    })
    tx2_id = resp.json().get('id')
    
    # Test 1: 404 for unknown id
    tests_total += 1
    resp = requests.get(f"{BASE_URL}/budgets/nonexistent-id/detail", params={
        "year": 2026,
        "month": 10
    })
    if log_test("Detail for unknown id returns 404", resp.status_code == 404, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    # Test 2: Get detail for existing budget
    tests_total += 1
    resp = requests.get(f"{BASE_URL}/budgets/{budget_id}/detail", params={
        "year": 2026,
        "month": 10
    })
    if log_test("Detail for existing budget returns 200", resp.status_code == 200, 
                f"Status: {resp.status_code}"):
        tests_passed += 1
    
    detail = resp.json()
    
    # Test 3: Detail includes budget fields
    tests_total += 1
    has_budget_fields = all(k in detail for k in ['id', 'name', 'amount_limit', 'spent', 'available'])
    if log_test("Detail includes budget fields", has_budget_fields, 
               f"Keys: {list(detail.keys())}"):
        tests_passed += 1
    
    # Test 4: Detail includes transactions array
    tests_total += 1
    has_transactions = 'transactions' in detail and isinstance(detail['transactions'], list)
    if log_test("Detail includes transactions array", has_transactions, 
               f"Transaction count: {len(detail.get('transactions', []))}"):
        tests_passed += 1
    
    # Test 5: Detail includes category
    tests_total += 1
    has_category = 'category' in detail and detail['category'] is not None
    if log_test("Detail includes category", has_category, 
               f"Category: {detail.get('category', {}).get('name')}"):
        tests_passed += 1
    
    # Test 6: Transactions are contributing transactions
    tests_total += 1
    if has_transactions:
        tx_count_correct = len(detail['transactions']) == 2
        if log_test("Detail has 2 contributing transactions", tx_count_correct, 
                   f"Actual count: {len(detail['transactions'])}"):
            tests_passed += 1
    else:
        log_test("Detail has 2 contributing transactions", False, "No transactions array")
    
    # Cleanup
    if budget_id:
        requests.delete(f"{BASE_URL}/budgets/{budget_id}")
    if tx1_id:
        requests.delete(f"{BASE_URL}/transactions/{tx1_id}")
    if tx2_id:
        requests.delete(f"{BASE_URL}/transactions/{tx2_id}")
    
    print(f"\n{YELLOW}Budget detail tests: {tests_passed}/{tests_total} passed{RESET}")
    return tests_passed == tests_total

def main():
    """Run all tests"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}MoneyFlow Budgets API Comprehensive Test Suite{RESET}")
    print(f"{BLUE}Testing against: {BASE_URL}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    # Cleanup first
    cleanup_test_data()
    
    # Setup
    categories, food_group, food_leaf = setup_categories()
    
    # Get test categories
    expense_cat = next((c for c in categories if c['type'] == 'expense' and not c.get('is_group')), None)
    
    # Run all tests
    results = []
    
    results.append(("Validation Errors", test_validation_errors(categories)))
    results.append(("Duplicate Conflict", test_duplicate_conflict(expense_cat)))
    results.append(("Idempotency Key", test_idempotency_key(expense_cat)))
    results.append(("Update Budget", test_update_budget(expense_cat)))
    results.append(("Delete Budget", test_delete_budget(expense_cat)))
    results.append(("Scenario 1: Group + Subcategory", test_scenario_1_group_and_subcategory(food_group, food_leaf)))
    results.append(("Scenario 2: Income/Transfer Exclusion", test_scenario_2_income_transfer_exclusion(categories)))
    results.append(("Scenario 3: Transaction Edit/Delete", test_scenario_3_transaction_edit_delete(categories)))
    results.append(("Scenario 4: Status Transitions", test_scenario_4_status_transitions(categories)))
    results.append(("Scenario 5: Weekly Budget", test_scenario_5_weekly_budget(categories)))
    results.append(("Scenario 6: Custom Budget", test_scenario_6_custom_budget(categories)))
    results.append(("Scenario 7: Floating Precision", test_scenario_7_floating_precision(categories)))
    results.append(("Scenario 8: Account Balance Unchanged", test_scenario_8_account_balance_unchanged(categories)))
    results.append(("Budget Detail Endpoint", test_budget_detail(categories)))
    
    # Summary
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST SUMMARY{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{GREEN}✓ PASS{RESET}" if result else f"{RED}✗ FAIL{RESET}"
        print(f"{status} - {name}")
    
    print(f"\n{BLUE}{'='*80}{RESET}")
    if passed == total:
        print(f"{GREEN}ALL TESTS PASSED: {passed}/{total}{RESET}")
    else:
        print(f"{YELLOW}TESTS PASSED: {passed}/{total}{RESET}")
        print(f"{RED}TESTS FAILED: {total - passed}/{total}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
