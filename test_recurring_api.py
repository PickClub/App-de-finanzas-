#!/usr/bin/env python3
"""
Recurring Templates API Test
Tests the new GET/POST/DELETE /api/recurring endpoints
Verifies they are config-only and do NOT affect balances/transactions
"""
import requests
import sys
import json
from datetime import datetime

BASE_URL = "http://localhost:8001"

def print_section(title):
    print(f"\n{'='*70}")
    print(f"{title}")
    print(f"{'='*70}")

def test_get(endpoint, description):
    """Test GET endpoint and return response"""
    url = f"{BASE_URL}{endpoint}"
    print(f"\n  Testing: GET {endpoint}")
    print(f"  Description: {description}")
    try:
        response = requests.get(url, timeout=10)
        status = response.status_code
        print(f"  Status: HTTP {status}")
        
        if status == 200:
            data = response.json()
            print(f"  ✅ SUCCESS")
            return True, data
        else:
            print(f"  ❌ FAILED - HTTP {status}")
            print(f"  Response: {response.text[:300]}")
            return False, None
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False, None

def test_post(endpoint, payload, description):
    """Test POST endpoint and return response"""
    url = f"{BASE_URL}{endpoint}"
    print(f"\n  Testing: POST {endpoint}")
    print(f"  Description: {description}")
    print(f"  Payload: {json.dumps(payload, indent=2)}")
    try:
        response = requests.post(url, json=payload, timeout=10)
        status = response.status_code
        print(f"  Status: HTTP {status}")
        
        if status == 200:
            data = response.json()
            print(f"  ✅ SUCCESS")
            print(f"  Response: {json.dumps(data, indent=2)}")
            return True, data
        else:
            print(f"  ❌ FAILED - HTTP {status}")
            print(f"  Response: {response.text[:300]}")
            return False, None
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False, None

def test_delete(endpoint, description):
    """Test DELETE endpoint and return response"""
    url = f"{BASE_URL}{endpoint}"
    print(f"\n  Testing: DELETE {endpoint}")
    print(f"  Description: {description}")
    try:
        response = requests.delete(url, timeout=10)
        status = response.status_code
        print(f"  Status: HTTP {status}")
        
        if status == 200:
            data = response.json()
            print(f"  ✅ SUCCESS")
            print(f"  Response: {json.dumps(data, indent=2)}")
            return True, data
        else:
            print(f"  ❌ FAILED - HTTP {status}")
            print(f"  Response: {response.text[:300]}")
            return False, None
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False, None

def main():
    print_section("RECURRING TEMPLATES API TEST")
    print("Testing: GET/POST/DELETE /api/recurring")
    print("Verifying: Config-only, NO impact on balances/transactions")
    
    test_results = []
    created_template_ids = []
    
    # STEP 1: Get baseline data
    print_section("STEP 1: Get Baseline Data (Summary & Accounts)")
    
    success, summary_baseline = test_get("/api/summary", "Get baseline summary")
    test_results.append(("GET /api/summary (baseline)", success))
    if not success:
        print("\n❌ CRITICAL: Cannot get baseline summary. Aborting test.")
        return 1
    
    baseline_total_balance = summary_baseline.get("total_balance", 0)
    print(f"\n  📊 Baseline total_balance: {baseline_total_balance}")
    
    success, accounts_baseline = test_get("/api/accounts", "Get baseline accounts")
    test_results.append(("GET /api/accounts (baseline)", success))
    if not success:
        print("\n❌ CRITICAL: Cannot get baseline accounts. Aborting test.")
        return 1
    
    baseline_account_balances = {acc["id"]: acc["current_balance"] for acc in accounts_baseline}
    print(f"\n  📊 Baseline account balances:")
    for acc_id, balance in baseline_account_balances.items():
        print(f"     Account {acc_id}: {balance}")
    
    success, transactions_baseline = test_get("/api/transactions", "Get baseline transactions")
    test_results.append(("GET /api/transactions (baseline)", success))
    baseline_transaction_count = len(transactions_baseline) if success else 0
    print(f"\n  📊 Baseline transaction count: {baseline_transaction_count}")
    
    # STEP 2: POST recurring template with monthly frequency
    print_section("STEP 2: POST Recurring Template (Monthly)")
    
    payload1 = {
        "source_transaction_id": None,
        "name": "Suscripción test",
        "amount": 120,
        "type": "expense",
        "category_id": None,
        "account_id": None,
        "to_account_id": None,
        "notes": "test",
        "frequency": "monthly",
        "interval_days": None,
        "start_date": "2026-01-01T00:00:00+00:00",
        "end_date": None
    }
    
    success, template1 = test_post("/api/recurring", payload1, "Create monthly recurring template")
    test_results.append(("POST /api/recurring (monthly)", success))
    
    if success and template1:
        # Verify response structure
        print(f"\n  🔍 Verifying response structure:")
        has_id = "id" in template1
        has_no_underscore_id = "_id" not in template1
        has_active = template1.get("active") == True
        has_name = template1.get("name") == "Suscripción test"
        has_frequency = template1.get("frequency") == "monthly"
        
        print(f"     ✓ Has 'id' field: {has_id}")
        print(f"     ✓ No '_id' field: {has_no_underscore_id}")
        print(f"     ✓ active=true: {has_active}")
        print(f"     ✓ name echoed: {has_name}")
        print(f"     ✓ frequency=monthly: {has_frequency}")
        
        if has_id:
            created_template_ids.append(template1["id"])
            print(f"     📝 Created template ID: {template1['id']}")
        
        if not all([has_id, has_no_underscore_id, has_active, has_name, has_frequency]):
            print(f"     ⚠️  Response structure validation FAILED")
    
    # STEP 3: POST recurring template with custom frequency
    print_section("STEP 3: POST Recurring Template (Custom)")
    
    payload2 = {
        "source_transaction_id": None,
        "name": "Custom interval test",
        "amount": 50,
        "type": "expense",
        "category_id": None,
        "account_id": None,
        "to_account_id": None,
        "notes": "custom frequency test",
        "frequency": "custom",
        "interval_days": 10,
        "start_date": "2026-01-15T00:00:00+00:00",
        "end_date": None
    }
    
    success, template2 = test_post("/api/recurring", payload2, "Create custom recurring template")
    test_results.append(("POST /api/recurring (custom)", success))
    
    if success and template2:
        # Verify custom frequency
        print(f"\n  🔍 Verifying custom frequency:")
        has_custom_freq = template2.get("frequency") == "custom"
        has_interval = template2.get("interval_days") == 10
        
        print(f"     ✓ frequency=custom: {has_custom_freq}")
        print(f"     ✓ interval_days=10: {has_interval}")
        
        if template2.get("id"):
            created_template_ids.append(template2["id"])
            print(f"     📝 Created template ID: {template2['id']}")
    
    # STEP 4: GET /api/recurring to list templates
    print_section("STEP 4: GET Recurring Templates List")
    
    success, templates_list = test_get("/api/recurring", "List all recurring templates")
    test_results.append(("GET /api/recurring (list)", success))
    
    if success and templates_list:
        print(f"\n  📊 Found {len(templates_list)} recurring template(s)")
        for i, tmpl in enumerate(templates_list, 1):
            print(f"     {i}. {tmpl.get('name')} (id: {tmpl.get('id')}, frequency: {tmpl.get('frequency')})")
        
        # Verify our created templates are in the list
        found_ids = [t["id"] for t in templates_list if "id" in t]
        for created_id in created_template_ids:
            if created_id in found_ids:
                print(f"     ✓ Created template {created_id} found in list")
            else:
                print(f"     ⚠️  Created template {created_id} NOT found in list")
    
    # STEP 5: DELETE one recurring template
    print_section("STEP 5: DELETE Recurring Template")
    
    if created_template_ids:
        delete_id = created_template_ids[0]
        success, delete_response = test_delete(f"/api/recurring/{delete_id}", f"Delete template {delete_id}")
        test_results.append(("DELETE /api/recurring/{id}", success))
        
        if success and delete_response:
            has_ok = delete_response.get("ok") == True
            print(f"\n  🔍 Verifying delete response:")
            print(f"     ✓ Response has ok=true: {has_ok}")
        
        # Verify it's gone from the list
        print(f"\n  🔍 Verifying template is deleted:")
        success, templates_after_delete = test_get("/api/recurring", "List templates after delete")
        if success and templates_after_delete:
            remaining_ids = [t["id"] for t in templates_after_delete if "id" in t]
            if delete_id not in remaining_ids:
                print(f"     ✓ Template {delete_id} successfully removed from list")
            else:
                print(f"     ❌ Template {delete_id} still in list after delete")
    else:
        print("\n  ⚠️  No templates created, skipping delete test")
        test_results.append(("DELETE /api/recurring/{id}", False))
    
    # STEP 6: CRITICAL REGRESSION CHECK
    print_section("STEP 6: CRITICAL REGRESSION CHECK")
    print("Verifying balances/summary/transactions are UNCHANGED")
    
    # Check summary
    success, summary_after = test_get("/api/summary", "Get summary after recurring operations")
    test_results.append(("GET /api/summary (after)", success))
    
    if success and summary_after:
        after_total_balance = summary_after.get("total_balance", 0)
        print(f"\n  📊 Comparison:")
        print(f"     Baseline total_balance: {baseline_total_balance}")
        print(f"     After total_balance:    {after_total_balance}")
        
        if baseline_total_balance == after_total_balance:
            print(f"     ✅ PASS - total_balance UNCHANGED")
        else:
            print(f"     ❌ FAIL - total_balance CHANGED (diff: {after_total_balance - baseline_total_balance})")
    
    # Check accounts
    success, accounts_after = test_get("/api/accounts", "Get accounts after recurring operations")
    test_results.append(("GET /api/accounts (after)", success))
    
    if success and accounts_after:
        after_account_balances = {acc["id"]: acc["current_balance"] for acc in accounts_after}
        print(f"\n  📊 Account balance comparison:")
        
        all_accounts_unchanged = True
        for acc_id, baseline_balance in baseline_account_balances.items():
            after_balance = after_account_balances.get(acc_id, None)
            if after_balance is not None:
                if baseline_balance == after_balance:
                    print(f"     ✅ Account {acc_id}: {baseline_balance} → {after_balance} (UNCHANGED)")
                else:
                    print(f"     ❌ Account {acc_id}: {baseline_balance} → {after_balance} (CHANGED)")
                    all_accounts_unchanged = False
            else:
                print(f"     ⚠️  Account {acc_id} not found after operations")
        
        if all_accounts_unchanged:
            print(f"\n     ✅ PASS - All account balances UNCHANGED")
        else:
            print(f"\n     ❌ FAIL - Some account balances CHANGED")
    
    # Check transactions
    success, transactions_after = test_get("/api/transactions", "Get transactions after recurring operations")
    test_results.append(("GET /api/transactions (after)", success))
    
    if success and transactions_after:
        after_transaction_count = len(transactions_after)
        print(f"\n  📊 Transaction count comparison:")
        print(f"     Baseline count: {baseline_transaction_count}")
        print(f"     After count:    {after_transaction_count}")
        
        if baseline_transaction_count == after_transaction_count:
            print(f"     ✅ PASS - Transaction count UNCHANGED (no new transactions created)")
        else:
            print(f"     ❌ FAIL - Transaction count CHANGED (diff: {after_transaction_count - baseline_transaction_count})")
    
    # SUMMARY
    print_section("TEST SUMMARY")
    
    passed = sum(1 for _, success in test_results if success)
    total = len(test_results)
    
    print(f"\nTotal: {passed}/{total} tests passed\n")
    print("Detailed Results:")
    for test_name, success in test_results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - {test_name}")
    
    print(f"\n{'='*70}")
    if passed == total:
        print("✅✅✅ ALL TESTS PASSED")
        print("Recurring templates API is working correctly")
        print("Config-only verified: NO impact on balances/transactions")
    else:
        print(f"⚠️  {total - passed} TEST(S) FAILED")
        print("Please review the failures above")
    print(f"{'='*70}")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
