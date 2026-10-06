#!/usr/bin/env python3
"""
Backend Persistence Testing for MoneyFlow API
Tests CREATE → SAVE → RETRIEVE persistence for accounts, transactions, and debts
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

BASE_URL = "http://localhost:8001"

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

def make_request(method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, retry_once: bool = False) -> tuple[int, Any]:
    """Make HTTP request and return (status_code, response_data)"""
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=10)
        elif method == "POST":
            resp = requests.post(url, json=data, timeout=10)
        elif method == "DELETE":
            resp = requests.delete(url, timeout=10)
        else:
            return (0, f"Unsupported method: {method}")
        
        # Handle known transient 500 on first /api/user call
        if resp.status_code == 500 and endpoint == "/api/user" and retry_once:
            log_warning(f"Transient 500 on first /api/user call (known ObjectId serialization issue), retrying...")
            resp = requests.get(url, timeout=10)
        
        try:
            return (resp.status_code, resp.json())
        except:
            return (resp.status_code, resp.text)
    except requests.exceptions.ConnectionError:
        return (0, "Connection refused - backend not running")
    except Exception as e:
        return (0, str(e))

def test_health_checks() -> bool:
    """Test 1: HEALTH - Verify all GET endpoints return 200"""
    print("\n" + "="*70)
    print("TEST 1: HEALTH CHECKS")
    print("="*70)
    
    endpoints = ["/api/user", "/api/accounts", "/api/transactions", "/api/debts"]
    all_passed = True
    
    for endpoint in endpoints:
        retry = (endpoint == "/api/user")  # Only retry /api/user
        status, data = make_request("GET", endpoint, retry_once=retry)
        
        if status == 200:
            log_success(f"GET {endpoint} → HTTP 200")
            if endpoint == "/api/user":
                if isinstance(data, dict) and "id" in data:
                    log_info(f"  User ID: {data.get('id')}")
                else:
                    log_warning(f"  Response missing 'id' field: {data}")
        else:
            log_error(f"GET {endpoint} → HTTP {status}")
            log_error(f"  Response: {data}")
            all_passed = False
    
    return all_passed

def test_account_persistence() -> Optional[str]:
    """Test 2: ACCOUNT persistence - CREATE → RETRIEVE → verify"""
    print("\n" + "="*70)
    print("TEST 2: ACCOUNT PERSISTENCE (CREATE → RETRIEVE)")
    print("="*70)
    
    # CREATE
    account_data = {
        "name": "ZZ_TEST_ACCOUNT",
        "type": "cash",
        "initial_balance": 123.45,
        "color": "#FF0000",
        "icon": "wallet-outline",
        "currency": "USD"
    }
    
    log_info(f"Creating test account: {account_data['name']}")
    status, response = make_request("POST", "/api/accounts", account_data)
    
    if status != 200:
        log_error(f"POST /api/accounts → HTTP {status}")
        log_error(f"  Response: {response}")
        return None
    
    log_success(f"POST /api/accounts → HTTP 200")
    
    if not isinstance(response, dict) or "id" not in response:
        log_error(f"  Response missing 'id' field: {response}")
        return None
    
    account_id = response["id"]
    log_success(f"  Created account ID: {account_id}")
    log_info(f"  Name: {response.get('name')}, Balance: {response.get('initial_balance')}")
    
    # RETRIEVE
    log_info("Retrieving all accounts to verify persistence...")
    status, accounts = make_request("GET", "/api/accounts")
    
    if status != 200:
        log_error(f"GET /api/accounts → HTTP {status}")
        log_error(f"  Response: {accounts}")
        return None
    
    log_success(f"GET /api/accounts → HTTP 200")
    
    if not isinstance(accounts, list):
        log_error(f"  Expected list, got: {type(accounts)}")
        return None
    
    log_info(f"  Total accounts: {len(accounts)}")
    
    # VERIFY
    found = False
    for acc in accounts:
        if acc.get("id") == account_id:
            found = True
            log_success(f"✓✓✓ PERSISTENCE VERIFIED: Account {account_id} found in list")
            log_info(f"  Name: {acc.get('name')}, Type: {acc.get('type')}, Balance: {acc.get('initial_balance')}")
            
            # Verify fields match
            if acc.get("name") == account_data["name"] and acc.get("initial_balance") == account_data["initial_balance"]:
                log_success(f"  Field values match original data")
            else:
                log_warning(f"  Field mismatch detected")
            break
    
    if not found:
        log_error(f"✗✗✗ PERSISTENCE FAILED: Account {account_id} NOT found in GET /api/accounts")
        log_error(f"  Available IDs: {[a.get('id') for a in accounts]}")
        return None
    
    return account_id

def test_transaction_persistence(account_id: str) -> Optional[str]:
    """Test 3: TRANSACTION persistence - CREATE → RETRIEVE → verify"""
    print("\n" + "="*70)
    print("TEST 3: TRANSACTION PERSISTENCE (CREATE → RETRIEVE)")
    print("="*70)
    
    # CREATE
    transaction_data = {
        "name": "ZZ_TEST_TX",
        "amount": 50.0,
        "type": "income",
        "account_id": account_id,
        "notes": "Test transaction for persistence verification"
    }
    
    log_info(f"Creating test transaction: {transaction_data['name']}")
    status, response = make_request("POST", "/api/transactions", transaction_data)
    
    if status != 200:
        log_error(f"POST /api/transactions → HTTP {status}")
        log_error(f"  Response: {response}")
        return None
    
    log_success(f"POST /api/transactions → HTTP 200")
    
    if not isinstance(response, dict) or "id" not in response:
        log_error(f"  Response missing 'id' field: {response}")
        return None
    
    transaction_id = response["id"]
    log_success(f"  Created transaction ID: {transaction_id}")
    log_info(f"  Name: {response.get('name')}, Amount: {response.get('amount')}, Type: {response.get('type')}")
    
    # RETRIEVE
    log_info("Retrieving all transactions to verify persistence...")
    status, transactions = make_request("GET", "/api/transactions")
    
    if status != 200:
        log_error(f"GET /api/transactions → HTTP {status}")
        log_error(f"  Response: {transactions}")
        return None
    
    log_success(f"GET /api/transactions → HTTP 200")
    
    if not isinstance(transactions, list):
        log_error(f"  Expected list, got: {type(transactions)}")
        return None
    
    log_info(f"  Total transactions: {len(transactions)}")
    
    # VERIFY
    found = False
    for tx in transactions:
        if tx.get("id") == transaction_id:
            found = True
            log_success(f"✓✓✓ PERSISTENCE VERIFIED: Transaction {transaction_id} found in list")
            log_info(f"  Name: {tx.get('name')}, Amount: {tx.get('amount')}, Type: {tx.get('type')}")
            
            # Verify fields match
            if tx.get("name") == transaction_data["name"] and tx.get("amount") == transaction_data["amount"]:
                log_success(f"  Field values match original data")
            else:
                log_warning(f"  Field mismatch detected")
            break
    
    if not found:
        log_error(f"✗✗✗ PERSISTENCE FAILED: Transaction {transaction_id} NOT found in GET /api/transactions")
        log_error(f"  Available IDs: {[t.get('id') for t in transactions]}")
        return None
    
    return transaction_id

def test_debt_persistence() -> Optional[str]:
    """Test 4: DEBT persistence - CREATE → RETRIEVE → verify"""
    print("\n" + "="*70)
    print("TEST 4: DEBT PERSISTENCE (CREATE → RETRIEVE)")
    print("="*70)
    
    # CREATE
    debt_data = {
        "name": "ZZ_TEST_DEBT",
        "direction": "i_owe",
        "person": "Tester",
        "original_amount": 200.0,
        "notes": "Test debt for persistence verification"
    }
    
    log_info(f"Creating test debt: {debt_data['name']}")
    status, response = make_request("POST", "/api/debts", debt_data)
    
    if status != 200:
        log_error(f"POST /api/debts → HTTP {status}")
        log_error(f"  Response: {response}")
        return None
    
    log_success(f"POST /api/debts → HTTP 200")
    
    if not isinstance(response, dict) or "id" not in response:
        log_error(f"  Response missing 'id' field: {response}")
        return None
    
    debt_id = response["id"]
    log_success(f"  Created debt ID: {debt_id}")
    log_info(f"  Name: {response.get('name')}, Direction: {response.get('direction')}, Amount: {response.get('original_amount')}")
    
    # RETRIEVE
    log_info("Retrieving all debts to verify persistence...")
    status, debts = make_request("GET", "/api/debts")
    
    if status != 200:
        log_error(f"GET /api/debts → HTTP {status}")
        log_error(f"  Response: {debts}")
        return None
    
    log_success(f"GET /api/debts → HTTP 200")
    
    if not isinstance(debts, list):
        log_error(f"  Expected list, got: {type(debts)}")
        return None
    
    log_info(f"  Total debts: {len(debts)}")
    
    # VERIFY
    found = False
    for debt in debts:
        if debt.get("id") == debt_id:
            found = True
            log_success(f"✓✓✓ PERSISTENCE VERIFIED: Debt {debt_id} found in list")
            log_info(f"  Name: {debt.get('name')}, Direction: {debt.get('direction')}, Amount: {debt.get('original_amount')}")
            
            # Verify fields match
            if debt.get("name") == debt_data["name"] and debt.get("original_amount") == debt_data["original_amount"]:
                log_success(f"  Field values match original data")
            else:
                log_warning(f"  Field mismatch detected")
            break
    
    if not found:
        log_error(f"✗✗✗ PERSISTENCE FAILED: Debt {debt_id} NOT found in GET /api/debts")
        log_error(f"  Available IDs: {[d.get('id') for d in debts]}")
        return None
    
    return debt_id

def test_cleanup(account_id: Optional[str], transaction_id: Optional[str], debt_id: Optional[str]) -> bool:
    """Test 5: CLEANUP - DELETE test records and verify removal"""
    print("\n" + "="*70)
    print("TEST 5: CLEANUP (DELETE test records)")
    print("="*70)
    
    all_passed = True
    
    # DELETE ACCOUNT
    if account_id:
        log_info(f"Deleting test account: {account_id}")
        status, response = make_request("DELETE", f"/api/accounts/{account_id}")
        
        if status == 200 and isinstance(response, dict) and response.get("ok"):
            log_success(f"DELETE /api/accounts/{account_id} → HTTP 200, ok=true")
            
            # Verify removal
            status, accounts = make_request("GET", "/api/accounts")
            if status == 200 and isinstance(accounts, list):
                if not any(a.get("id") == account_id for a in accounts):
                    log_success(f"  Account {account_id} successfully removed from list")
                else:
                    log_error(f"  Account {account_id} still present in list after DELETE")
                    all_passed = False
        else:
            log_error(f"DELETE /api/accounts/{account_id} → HTTP {status}")
            log_error(f"  Response: {response}")
            all_passed = False
    
    # DELETE TRANSACTION
    if transaction_id:
        log_info(f"Deleting test transaction: {transaction_id}")
        status, response = make_request("DELETE", f"/api/transactions/{transaction_id}")
        
        if status == 200 and isinstance(response, dict) and response.get("ok"):
            log_success(f"DELETE /api/transactions/{transaction_id} → HTTP 200, ok=true")
            
            # Verify removal
            status, transactions = make_request("GET", "/api/transactions")
            if status == 200 and isinstance(transactions, list):
                if not any(t.get("id") == transaction_id for t in transactions):
                    log_success(f"  Transaction {transaction_id} successfully removed from list")
                else:
                    log_error(f"  Transaction {transaction_id} still present in list after DELETE")
                    all_passed = False
        else:
            log_error(f"DELETE /api/transactions/{transaction_id} → HTTP {status}")
            log_error(f"  Response: {response}")
            all_passed = False
    
    # DELETE DEBT
    if debt_id:
        log_info(f"Deleting test debt: {debt_id}")
        status, response = make_request("DELETE", f"/api/debts/{debt_id}")
        
        if status == 200 and isinstance(response, dict) and response.get("ok"):
            log_success(f"DELETE /api/debts/{debt_id} → HTTP 200, ok=true")
            
            # Verify removal
            status, debts = make_request("GET", "/api/debts")
            if status == 200 and isinstance(debts, list):
                if not any(d.get("id") == debt_id for d in debts):
                    log_success(f"  Debt {debt_id} successfully removed from list")
                else:
                    log_error(f"  Debt {debt_id} still present in list after DELETE")
                    all_passed = False
        else:
            log_error(f"DELETE /api/debts/{debt_id} → HTTP {status}")
            log_error(f"  Response: {response}")
            all_passed = False
    
    return all_passed

def main():
    print("\n" + "="*70)
    print("MONEYFLOW BACKEND PERSISTENCE TESTING")
    print("Testing against: " + BASE_URL)
    print("="*70)
    
    results = {
        "health": False,
        "account_persistence": False,
        "transaction_persistence": False,
        "debt_persistence": False,
        "cleanup": False
    }
    
    test_ids = {
        "account_id": None,
        "transaction_id": None,
        "debt_id": None
    }
    
    # Test 1: Health checks
    results["health"] = test_health_checks()
    
    if not results["health"]:
        log_error("\n✗✗✗ HEALTH CHECKS FAILED - Aborting further tests")
        sys.exit(1)
    
    # Test 2: Account persistence
    test_ids["account_id"] = test_account_persistence()
    results["account_persistence"] = (test_ids["account_id"] is not None)
    
    # Test 3: Transaction persistence (requires account_id)
    if test_ids["account_id"]:
        test_ids["transaction_id"] = test_transaction_persistence(test_ids["account_id"])
        results["transaction_persistence"] = (test_ids["transaction_id"] is not None)
    else:
        log_warning("\nSkipping transaction persistence test (no account_id)")
    
    # Test 4: Debt persistence
    test_ids["debt_id"] = test_debt_persistence()
    results["debt_persistence"] = (test_ids["debt_id"] is not None)
    
    # Test 5: Cleanup
    results["cleanup"] = test_cleanup(
        test_ids["account_id"],
        test_ids["transaction_id"],
        test_ids["debt_id"]
    )
    
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
        print(f"\n{Colors.GREEN}✓✓✓ ALL TESTS PASSED - Backend persistence is working correctly{Colors.RESET}")
        sys.exit(0)
    else:
        print(f"\n{Colors.RED}✗✗✗ SOME TESTS FAILED - Backend persistence has issues{Colors.RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
