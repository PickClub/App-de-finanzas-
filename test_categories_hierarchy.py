#!/usr/bin/env python3
"""
Categories Hierarchy Testing for MoneyFlow API
Tests the NEW grouped Categories hierarchy feature with parent_id/is_group fields
"""

import requests
import json
import sys
from typing import Dict, Any, Optional, List

# Use the public backend URL
BASE_URL = "https://demo-view-38.preview.emergentagent.com/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def log_success(msg: str):
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")

def log_error(msg: str):
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")

def log_info(msg: str):
    print(f"{Colors.BLUE}ℹ {msg}{Colors.RESET}")

def log_warning(msg: str):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.RESET}")

def make_request(method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> tuple[int, Any]:
    """Make HTTP request and return (status_code, response_data)"""
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=10)
        elif method == "POST":
            resp = requests.post(url, json=data, timeout=10)
        elif method == "PUT":
            resp = requests.put(url, json=data, timeout=10)
        elif method == "DELETE":
            resp = requests.delete(url, timeout=10)
        else:
            return (0, f"Unsupported method: {method}")
        
        try:
            return (resp.status_code, resp.json())
        except:
            return (resp.status_code, resp.text)
    except requests.exceptions.ConnectionError:
        return (0, "Connection refused - backend not running")
    except Exception as e:
        return (0, str(e))

def test_data_protection_baseline() -> Dict[str, Any]:
    """Capture baseline data before any operations"""
    print("\n" + "="*70)
    print("BASELINE: Capturing data protection baseline")
    print("="*70)
    
    baseline = {}
    
    # Get transactions count
    status, transactions = make_request("GET", "/transactions")
    if status == 200 and isinstance(transactions, list):
        baseline["transactions_count"] = len(transactions)
        log_info(f"Baseline transactions count: {baseline['transactions_count']}")
    else:
        log_error(f"Failed to get transactions: HTTP {status}")
        baseline["transactions_count"] = None
    
    # Get summary total_balance
    status, summary = make_request("GET", "/summary")
    if status == 200 and isinstance(summary, dict):
        baseline["total_balance"] = summary.get("total_balance")
        log_info(f"Baseline total_balance: {baseline['total_balance']}")
    else:
        log_error(f"Failed to get summary: HTTP {status}")
        baseline["total_balance"] = None
    
    # Check for Motica category
    status, categories = make_request("GET", "/categories")
    if status == 200 and isinstance(categories, list):
        motica = next((c for c in categories if c.get("name") == "Motica"), None)
        if motica:
            baseline["motica"] = {
                "id": motica.get("id"),
                "name": motica.get("name"),
                "type": motica.get("type"),
                "icon": motica.get("icon"),
                "color": motica.get("color"),
                "parent_id": motica.get("parent_id"),
                "is_group": motica.get("is_group", False)
            }
            log_info(f"Baseline Motica category found: id={motica.get('id')}, parent_id={motica.get('parent_id')}")
        else:
            baseline["motica"] = None
            log_warning("Motica category not found in baseline")
    else:
        log_error(f"Failed to get categories: HTTP {status}")
        baseline["motica"] = None
    
    return baseline

def test_hierarchy_structure() -> bool:
    """Test 1: GET /api/categories returns groups and subcategories with correct structure"""
    print("\n" + "="*70)
    print("TEST 1: HIERARCHY STRUCTURE")
    print("="*70)
    
    status, categories = make_request("GET", "/categories")
    
    if status != 200:
        log_error(f"GET /categories → HTTP {status}")
        log_error(f"  Response: {categories}")
        return False
    
    log_success(f"GET /categories → HTTP 200")
    
    if not isinstance(categories, list):
        log_error(f"  Expected list, got: {type(categories)}")
        return False
    
    log_info(f"  Total categories: {len(categories)}")
    
    # Check for _id leakage
    has_id_leak = False
    for cat in categories:
        if "_id" in cat:
            log_error(f"  ✗ _id field leaked in category: {cat.get('name')}")
            has_id_leak = True
    
    if not has_id_leak:
        log_success("  ✓ No _id field leakage detected")
    
    # Separate groups and leaves
    groups = [c for c in categories if c.get("is_group") == True]
    leaves = [c for c in categories if c.get("is_group") != True]
    
    log_info(f"  Groups (is_group=true): {len(groups)}")
    log_info(f"  Leaves (is_group=false or unset): {len(leaves)}")
    
    # Check for exactly 12 groups
    if len(groups) != 12:
        log_error(f"  ✗ Expected exactly 12 groups, found {len(groups)}")
        return False
    
    log_success(f"  ✓ Found exactly 12 groups")
    
    # Verify 8 expense groups and 4 income groups
    expense_groups = [g for g in groups if g.get("type") == "expense"]
    income_groups = [g for g in groups if g.get("type") == "income"]
    
    expected_expense_groups = [
        "Food & Dining", "Home & Housing", "Transport & Auto", "Shopping & Goods",
        "Health & Wellness", "Entertainment & Leisure", "Finance", "Other & Misc"
    ]
    expected_income_groups = ["Work", "Investing", "Selling", "Other Earnings"]
    
    log_info(f"  Expense groups: {len(expense_groups)}")
    log_info(f"  Income groups: {len(income_groups)}")
    
    if len(expense_groups) != 8:
        log_error(f"  ✗ Expected 8 expense groups, found {len(expense_groups)}")
        return False
    
    if len(income_groups) != 4:
        log_error(f"  ✗ Expected 4 income groups, found {len(income_groups)}")
        return False
    
    log_success(f"  ✓ Found 8 expense groups and 4 income groups")
    
    # Verify group names
    expense_group_names = [g.get("name") for g in expense_groups]
    income_group_names = [g.get("name") for g in income_groups]
    
    missing_expense = [name for name in expected_expense_groups if name not in expense_group_names]
    missing_income = [name for name in expected_income_groups if name not in income_group_names]
    
    if missing_expense:
        log_error(f"  ✗ Missing expense groups: {missing_expense}")
        return False
    
    if missing_income:
        log_error(f"  ✗ Missing income groups: {missing_income}")
        return False
    
    log_success(f"  ✓ All expected group names present")
    
    # Verify groups have parent_id=null
    groups_with_parent = [g for g in groups if g.get("parent_id") is not None]
    if groups_with_parent:
        log_error(f"  ✗ Groups should have parent_id=null, but found {len(groups_with_parent)} with parent_id set")
        for g in groups_with_parent:
            log_error(f"    - {g.get('name')} has parent_id={g.get('parent_id')}")
        return False
    
    log_success(f"  ✓ All groups have parent_id=null")
    
    # Verify leaves with parent_id
    leaves_with_parent = [l for l in leaves if l.get("parent_id") is not None]
    log_info(f"  Leaves with parent_id: {len(leaves_with_parent)}")
    
    return not has_id_leak

def test_idempotency() -> bool:
    """Test 2: POST /api/categories/init-defaults idempotency"""
    print("\n" + "="*70)
    print("TEST 2: IDEMPOTENCY")
    print("="*70)
    
    # Get initial category count
    status, categories_before = make_request("GET", "/categories")
    if status != 200:
        log_error(f"Failed to get initial categories: HTTP {status}")
        return False
    
    initial_count = len(categories_before)
    log_info(f"Initial category count: {initial_count}")
    
    # First call to init-defaults
    log_info("Calling POST /categories/init-defaults (1st time)...")
    status1, response1 = make_request("POST", "/categories/init-defaults")
    
    if status1 != 200:
        log_error(f"POST /categories/init-defaults (1st) → HTTP {status1}")
        log_error(f"  Response: {response1}")
        return False
    
    log_success(f"POST /categories/init-defaults (1st) → HTTP 200")
    log_info(f"  Response: {json.dumps(response1, indent=2)}")
    
    first_total = response1.get("total")
    
    # Second call to init-defaults
    log_info("Calling POST /categories/init-defaults (2nd time)...")
    status2, response2 = make_request("POST", "/categories/init-defaults")
    
    if status2 != 200:
        log_error(f"POST /categories/init-defaults (2nd) → HTTP {status2}")
        log_error(f"  Response: {response2}")
        return False
    
    log_success(f"POST /categories/init-defaults (2nd) → HTTP 200")
    log_info(f"  Response: {json.dumps(response2, indent=2)}")
    
    # Verify idempotency: created=0, groups_created=0, links=0
    if response2.get("created") != 0:
        log_error(f"  ✗ Expected created=0 on 2nd call, got {response2.get('created')}")
        return False
    
    if response2.get("groups_created") != 0:
        log_error(f"  ✗ Expected groups_created=0 on 2nd call, got {response2.get('groups_created')}")
        return False
    
    if response2.get("links") != 0:
        log_error(f"  ✗ Expected links=0 on 2nd call, got {response2.get('links')}")
        return False
    
    log_success(f"  ✓ Idempotency verified: created=0, groups_created=0, links=0")
    
    # Third call to init-defaults
    log_info("Calling POST /categories/init-defaults (3rd time)...")
    status3, response3 = make_request("POST", "/categories/init-defaults")
    
    if status3 != 200:
        log_error(f"POST /categories/init-defaults (3rd) → HTTP {status3}")
        return False
    
    log_success(f"POST /categories/init-defaults (3rd) → HTTP 200")
    
    if response3.get("created") != 0 or response3.get("groups_created") != 0 or response3.get("links") != 0:
        log_error(f"  ✗ 3rd call not idempotent: {response3}")
        return False
    
    log_success(f"  ✓ 3rd call also idempotent")
    
    # Verify total count remains stable
    if response2.get("total") != first_total:
        log_error(f"  ✗ Total count changed: {first_total} → {response2.get('total')}")
        return False
    
    if response3.get("total") != first_total:
        log_error(f"  ✗ Total count changed: {first_total} → {response3.get('total')}")
        return False
    
    log_success(f"  ✓ Total count stable across calls: {first_total}")
    
    # Verify GET /categories count doesn't grow
    status, categories_after = make_request("GET", "/categories")
    if status != 200:
        log_error(f"Failed to get final categories: HTTP {status}")
        return False
    
    final_count = len(categories_after)
    if final_count != first_total:
        log_error(f"  ✗ GET /categories count mismatch: expected {first_total}, got {final_count}")
        return False
    
    log_success(f"  ✓ GET /categories count unchanged: {final_count}")
    
    return True

def test_hierarchy_correctness() -> bool:
    """Test 3: Verify hierarchy correctness by resolving parent_id->group name"""
    print("\n" + "="*70)
    print("TEST 3: HIERARCHY CORRECTNESS")
    print("="*70)
    
    status, categories = make_request("GET", "/categories")
    if status != 200:
        log_error(f"Failed to get categories: HTTP {status}")
        return False
    
    # Build lookup maps
    groups = {c["id"]: c for c in categories if c.get("is_group") == True}
    leaves = [c for c in categories if c.get("is_group") != True]
    
    # Helper to get children of a group
    def get_children(group_name: str, group_type: str) -> List[str]:
        group = next((g for g in groups.values() if g.get("name") == group_name and g.get("type") == group_type), None)
        if not group:
            return []
        group_id = group["id"]
        return [l.get("name") for l in leaves if l.get("parent_id") == group_id]
    
    all_passed = True
    
    # Test Shopping & Goods: must have 6 children including Electronics, Home, Beauty
    shopping_children = get_children("Shopping & Goods", "expense")
    log_info(f"Shopping & Goods children: {shopping_children}")
    
    if len(shopping_children) != 6:
        log_error(f"  ✗ Shopping & Goods should have 6 children, found {len(shopping_children)}")
        all_passed = False
    else:
        log_success(f"  ✓ Shopping & Goods has 6 children")
    
    required_shopping = ["Electronics", "Home", "Beauty"]
    missing_shopping = [name for name in required_shopping if name not in shopping_children]
    if missing_shopping:
        log_error(f"  ✗ Shopping & Goods missing children: {missing_shopping}")
        all_passed = False
    else:
        log_success(f"  ✓ Shopping & Goods contains Electronics, Home, Beauty")
    
    # Test Other & Misc: must contain Technology
    other_children = get_children("Other & Misc", "expense")
    log_info(f"Other & Misc children: {other_children}")
    
    if "Technology" not in other_children:
        log_error(f"  ✗ Other & Misc should contain Technology")
        all_passed = False
    else:
        log_success(f"  ✓ Other & Misc contains Technology")
    
    # Test Health & Wellness: must contain Personal Care
    health_children = get_children("Health & Wellness", "expense")
    log_info(f"Health & Wellness children: {health_children}")
    
    if "Personal Care" not in health_children:
        log_error(f"  ✗ Health & Wellness should contain Personal Care")
        all_passed = False
    else:
        log_success(f"  ✓ Health & Wellness contains Personal Care")
    
    # Test Work: must have 4 children
    work_children = get_children("Work", "income")
    log_info(f"Work children: {work_children}")
    
    if len(work_children) != 4:
        log_error(f"  ✗ Work should have 4 children, found {len(work_children)}")
        all_passed = False
    else:
        log_success(f"  ✓ Work has 4 children")
    
    # Test Investing: must have 2 children
    investing_children = get_children("Investing", "income")
    log_info(f"Investing children: {investing_children}")
    
    if len(investing_children) != 2:
        log_error(f"  ✗ Investing should have 2 children, found {len(investing_children)}")
        all_passed = False
    else:
        log_success(f"  ✓ Investing has 2 children")
    
    # Test Selling: must have 1 child
    selling_children = get_children("Selling", "income")
    log_info(f"Selling children: {selling_children}")
    
    if len(selling_children) != 1:
        log_error(f"  ✗ Selling should have 1 child, found {len(selling_children)}")
        all_passed = False
    else:
        log_success(f"  ✓ Selling has 1 child")
    
    # Test Other Earnings: must have 3 children
    other_earnings_children = get_children("Other Earnings", "income")
    log_info(f"Other Earnings children: {other_earnings_children}")
    
    if len(other_earnings_children) != 3:
        log_error(f"  ✗ Other Earnings should have 3 children, found {len(other_earnings_children)}")
        all_passed = False
    else:
        log_success(f"  ✓ Other Earnings has 3 children")
    
    return all_passed

def test_crud_with_hierarchy() -> bool:
    """Test 4: CRUD operations with hierarchy (parent_id preservation)"""
    print("\n" + "="*70)
    print("TEST 4: CRUD WITH HIERARCHY")
    print("="*70)
    
    # Get Shopping & Goods group id
    status, categories = make_request("GET", "/categories")
    if status != 200:
        log_error(f"Failed to get categories: HTTP {status}")
        return False
    
    shopping_group = next((c for c in categories if c.get("name") == "Shopping & Goods" and c.get("is_group") == True), None)
    if not shopping_group:
        log_error("Shopping & Goods group not found")
        return False
    
    shopping_id = shopping_group["id"]
    log_info(f"Shopping & Goods group id: {shopping_id}")
    
    # CREATE subcategory with parent_id
    log_info("Creating test subcategory ZZ_TESTSUB with parent_id...")
    create_data = {
        "name": "ZZ_TESTSUB",
        "type": "expense",
        "icon": "star-outline",
        "color": "#123456",
        "is_group": False,
        "parent_id": shopping_id
    }
    
    status, response = make_request("POST", "/categories", create_data)
    
    if status != 200:
        log_error(f"POST /categories → HTTP {status}")
        log_error(f"  Response: {response}")
        return False
    
    log_success(f"POST /categories → HTTP 200")
    
    if not isinstance(response, dict) or "id" not in response:
        log_error(f"  Response missing 'id' field: {response}")
        return False
    
    test_cat_id = response["id"]
    log_success(f"  Created category id: {test_cat_id}")
    
    # Verify response contains parent_id and is_group
    if response.get("parent_id") != shopping_id:
        log_error(f"  ✗ Expected parent_id={shopping_id}, got {response.get('parent_id')}")
        return False
    
    if response.get("is_group") != False:
        log_error(f"  ✗ Expected is_group=false, got {response.get('is_group')}")
        return False
    
    if "_id" in response:
        log_error(f"  ✗ _id field leaked in response")
        return False
    
    log_success(f"  ✓ Response contains parent_id={shopping_id}, is_group=false, no _id")
    
    # UPDATE with ONLY name (parent_id should be preserved)
    log_info("Updating category with ONLY name (testing exclude_unset)...")
    update_data = {
        "name": "ZZ_TESTSUB2",
        "type": "expense",
        "icon": "star-outline",
        "color": "#123456"
        # NO parent_id or is_group
    }
    
    status, response = make_request("PUT", f"/categories/{test_cat_id}", update_data)
    
    if status != 200:
        log_error(f"PUT /categories/{test_cat_id} → HTTP {status}")
        log_error(f"  Response: {response}")
        return False
    
    log_success(f"PUT /categories/{test_cat_id} → HTTP 200")
    
    # Verify parent_id is still preserved
    if response.get("parent_id") != shopping_id:
        log_error(f"  ✗ parent_id NOT preserved! Expected {shopping_id}, got {response.get('parent_id')}")
        return False
    
    log_success(f"  ✓ parent_id preserved after partial update: {response.get('parent_id')}")
    
    # UPDATE with parent_id=null
    log_info("Updating category with parent_id=null...")
    update_data2 = {
        "name": "ZZ_TESTSUB2",
        "type": "expense",
        "icon": "star-outline",
        "color": "#123456",
        "parent_id": None,
        "is_group": False
    }
    
    status, response = make_request("PUT", f"/categories/{test_cat_id}", update_data2)
    
    if status != 200:
        log_error(f"PUT /categories/{test_cat_id} → HTTP {status}")
        return False
    
    log_success(f"PUT /categories/{test_cat_id} → HTTP 200")
    
    if response.get("parent_id") is not None:
        log_error(f"  ✗ Expected parent_id=null, got {response.get('parent_id')}")
        return False
    
    log_success(f"  ✓ parent_id set to null successfully")
    
    # DELETE
    log_info(f"Deleting test category {test_cat_id}...")
    status, response = make_request("DELETE", f"/categories/{test_cat_id}")
    
    if status != 200:
        log_error(f"DELETE /categories/{test_cat_id} → HTTP {status}")
        log_error(f"  Response: {response}")
        return False
    
    if not isinstance(response, dict) or response.get("ok") != True:
        log_error(f"  ✗ Expected {{ok: true}}, got {response}")
        return False
    
    log_success(f"DELETE /categories/{test_cat_id} → HTTP 200, {{ok: true}}")
    
    # Verify deletion
    status, categories = make_request("GET", "/categories")
    if status == 200:
        if any(c.get("id") == test_cat_id for c in categories):
            log_error(f"  ✗ Category still exists after DELETE")
            return False
        log_success(f"  ✓ Category successfully removed from list")
    
    return True

def test_data_protection(baseline: Dict[str, Any]) -> bool:
    """Test 5: Verify data protection (transactions, balance, Motica unchanged)"""
    print("\n" + "="*70)
    print("TEST 5: DATA PROTECTION")
    print("="*70)
    
    all_passed = True
    
    # Check transactions count
    status, transactions = make_request("GET", "/transactions")
    if status == 200 and isinstance(transactions, list):
        current_count = len(transactions)
        if current_count != baseline.get("transactions_count"):
            log_error(f"  ✗ Transactions count changed: {baseline.get('transactions_count')} → {current_count}")
            all_passed = False
        else:
            log_success(f"  ✓ Transactions count unchanged: {current_count}")
    else:
        log_error(f"Failed to get transactions: HTTP {status}")
        all_passed = False
    
    # Check total_balance
    status, summary = make_request("GET", "/summary")
    if status == 200 and isinstance(summary, dict):
        current_balance = summary.get("total_balance")
        if current_balance != baseline.get("total_balance"):
            log_error(f"  ✗ Total balance changed: {baseline.get('total_balance')} → {current_balance}")
            all_passed = False
        else:
            log_success(f"  ✓ Total balance unchanged: {current_balance}")
    else:
        log_error(f"Failed to get summary: HTTP {status}")
        all_passed = False
    
    # Check Motica category
    status, categories = make_request("GET", "/categories")
    if status == 200 and isinstance(categories, list):
        motica = next((c for c in categories if c.get("name") == "Motica"), None)
        
        if baseline.get("motica") is None:
            if motica is not None:
                log_warning(f"  ⚠ Motica category appeared (was not in baseline)")
            else:
                log_info(f"  Motica category still not present (as expected)")
        else:
            if motica is None:
                log_error(f"  ✗ Motica category was DELETED!")
                all_passed = False
            else:
                # Verify all fields unchanged
                baseline_motica = baseline["motica"]
                changes = []
                
                if motica.get("id") != baseline_motica.get("id"):
                    changes.append(f"id: {baseline_motica.get('id')} → {motica.get('id')}")
                if motica.get("name") != baseline_motica.get("name"):
                    changes.append(f"name: {baseline_motica.get('name')} → {motica.get('name')}")
                if motica.get("icon") != baseline_motica.get("icon"):
                    changes.append(f"icon: {baseline_motica.get('icon')} → {motica.get('icon')}")
                if motica.get("color") != baseline_motica.get("color"):
                    changes.append(f"color: {baseline_motica.get('color')} → {motica.get('color')}")
                if motica.get("parent_id") != baseline_motica.get("parent_id"):
                    changes.append(f"parent_id: {baseline_motica.get('parent_id')} → {motica.get('parent_id')}")
                
                if changes:
                    log_error(f"  ✗ Motica category was MODIFIED:")
                    for change in changes:
                        log_error(f"    - {change}")
                    all_passed = False
                else:
                    log_success(f"  ✓ Motica category unchanged (id={motica.get('id')}, parent_id={motica.get('parent_id')})")
    else:
        log_error(f"Failed to get categories: HTTP {status}")
        all_passed = False
    
    return all_passed

def main():
    print("\n" + "="*70)
    print("MONEYFLOW CATEGORIES HIERARCHY TESTING")
    print("Testing against: " + BASE_URL)
    print("="*70)
    
    results = {
        "baseline": False,
        "hierarchy_structure": False,
        "idempotency": False,
        "hierarchy_correctness": False,
        "crud_with_hierarchy": False,
        "data_protection": False
    }
    
    # Capture baseline
    baseline = test_data_protection_baseline()
    results["baseline"] = (baseline.get("transactions_count") is not None and baseline.get("total_balance") is not None)
    
    if not results["baseline"]:
        log_error("\n✗✗✗ BASELINE CAPTURE FAILED - Aborting tests")
        sys.exit(1)
    
    # Test 1: Hierarchy structure
    results["hierarchy_structure"] = test_hierarchy_structure()
    
    # Test 2: Idempotency
    results["idempotency"] = test_idempotency()
    
    # Test 3: Hierarchy correctness
    results["hierarchy_correctness"] = test_hierarchy_correctness()
    
    # Test 4: CRUD with hierarchy
    results["crud_with_hierarchy"] = test_crud_with_hierarchy()
    
    # Test 5: Data protection
    results["data_protection"] = test_data_protection(baseline)
    
    # Final summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    
    for test_name, passed in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.RESET}" if passed else f"{Colors.RED}✗ FAIL{Colors.RESET}"
        print(f"{test_name.upper().replace('_', ' ')}: {status}")
    
    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print(f"\n{Colors.GREEN}✓✓✓ ALL TESTS PASSED - Categories hierarchy feature working correctly{Colors.RESET}")
        sys.exit(0)
    else:
        print(f"\n{Colors.RED}✗✗✗ SOME TESTS FAILED - Categories hierarchy has issues{Colors.RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
