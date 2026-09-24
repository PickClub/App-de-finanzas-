#!/usr/bin/env python3
"""
READ-ONLY Backend API Verification Test
Tests all GET endpoints against localhost:8001
NO data creation, modification, or deletion
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8001"

def test_endpoint(method, path, description):
    """Test a single endpoint and return result"""
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        else:
            return {"status": "SKIP", "reason": f"Method {method} not allowed in READ-ONLY mode"}
        
        result = {
            "endpoint": path,
            "method": method,
            "status_code": response.status_code,
            "description": description,
            "success": response.status_code == 200
        }
        
        # Try to parse JSON response
        try:
            result["response_type"] = type(response.json()).__name__
            if isinstance(response.json(), dict):
                result["response_keys"] = list(response.json().keys())
            elif isinstance(response.json(), list):
                result["response_length"] = len(response.json())
        except:
            result["response_type"] = "non-json"
        
        return result
    except Exception as e:
        return {
            "endpoint": path,
            "method": method,
            "status_code": "ERROR",
            "description": description,
            "success": False,
            "error": str(e)
        }

def main():
    print("=" * 80)
    print("READ-ONLY Backend API Verification - 502 Bad Gateway Fix")
    print("=" * 80)
    print(f"Testing against: {BASE_URL}")
    print()
    
    # Define test cases - GET only
    test_cases = [
        ("GET", "/api/user", "Get user profile"),
        ("GET", "/api/accounts", "List accounts"),
        ("GET", "/api/summary", "Get financial summary"),
        ("GET", "/api/categories", "List categories"),
        ("GET", "/api/transactions", "List transactions"),
        ("GET", "/api/budgets", "List budgets"),
        ("GET", "/api/goals", "List goals"),
        ("GET", "/api/debts", "List debts"),
    ]
    
    results = []
    passed = 0
    failed = 0
    
    print("Testing endpoints...")
    print("-" * 80)
    
    for method, path, description in test_cases:
        result = test_endpoint(method, path, description)
        results.append(result)
        
        status_icon = "✅" if result["success"] else "❌"
        status_text = f"HTTP {result['status_code']}" if result['status_code'] != "ERROR" else "ERROR"
        
        print(f"{status_icon} {method:6} {path:25} → {status_text:12} | {description}")
        
        if result["success"]:
            passed += 1
            # Show response details for successful calls
            if "response_type" in result:
                if result["response_type"] == "dict" and "response_keys" in result:
                    print(f"   Response: dict with keys: {', '.join(result['response_keys'][:5])}")
                elif result["response_type"] == "list" and "response_length" in result:
                    print(f"   Response: array with {result['response_length']} items")
        else:
            failed += 1
            if "error" in result:
                print(f"   Error: {result['error']}")
    
    print("-" * 80)
    print()
    print("=" * 80)
    print(f"SUMMARY: {passed}/{len(test_cases)} endpoints passed")
    print("=" * 80)
    
    if failed == 0:
        print("✅ ALL ENDPOINTS PASSED - Backend is serving API correctly")
        print("✅ NO 502 Bad Gateway errors detected")
        return 0
    else:
        print(f"❌ {failed} endpoint(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
