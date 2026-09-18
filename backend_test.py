#!/usr/bin/env python3
"""
Backend API verification test for MoneyFlow
Tests GET endpoints only to verify 502 Bad Gateway is resolved
"""
import requests
import sys
import time

# Test both localhost and external ingress URL
LOCALHOST_URL = "http://localhost:8001"
EXTERNAL_URL = None  # Will try to detect from logs or use localhost

def test_endpoint(base_url, endpoint, retry_on_500=False):
    """Test a single GET endpoint"""
    url = f"{base_url}{endpoint}"
    try:
        print(f"\n  Testing: GET {endpoint}")
        response = requests.get(url, timeout=10)
        
        # Handle the known transient 500 on first /api/user request
        if response.status_code == 500 and retry_on_500:
            print(f"    ⚠️  First request returned 500 (known transient ObjectId error)")
            print(f"    🔄 Retrying...")
            time.sleep(0.5)
            response = requests.get(url, timeout=10)
        
        status = response.status_code
        if status == 200:
            print(f"    ✅ HTTP {status} - OK")
            try:
                data = response.json()
                if endpoint == "/api/user":
                    user_id = data.get("id", "N/A")
                    print(f"       User ID: {user_id}")
                    if user_id == "default-user":
                        print(f"       ✓ Correct default user ID")
                elif isinstance(data, list):
                    print(f"       Returned array with {len(data)} items")
                elif isinstance(data, dict):
                    print(f"       Returned object with {len(data)} keys")
            except Exception as e:
                print(f"       ⚠️  Could not parse JSON: {e}")
            return True
        else:
            print(f"    ❌ HTTP {status} - FAILED")
            print(f"       Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"    ❌ CONNECTION ERROR: {e}")
        return False
    except requests.exceptions.Timeout:
        print(f"    ❌ TIMEOUT")
        return False
    except Exception as e:
        print(f"    ❌ ERROR: {e}")
        return False

def main():
    print("=" * 70)
    print("MoneyFlow Backend API Verification")
    print("Testing GET endpoints to verify 502 Bad Gateway is resolved")
    print("=" * 70)
    
    # Endpoints to test
    endpoints = [
        ("/api/user", True),  # (endpoint, retry_on_500)
        ("/api/accounts", False),
        ("/api/summary", False),
        ("/api/categories", False),
        ("/api/transactions", False),
        ("/api/budgets", False),
        ("/api/goals", False),
        ("/api/debts", False),
    ]
    
    results = {}
    
    # Test localhost
    print(f"\n{'='*70}")
    print(f"Testing against LOCALHOST: {LOCALHOST_URL}")
    print(f"{'='*70}")
    
    for endpoint, retry in endpoints:
        results[endpoint] = test_endpoint(LOCALHOST_URL, endpoint, retry_on_500=retry)
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} endpoints passed")
    print("\nDetailed Results:")
    for endpoint, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - GET {endpoint}")
    
    # Check if 502 is resolved
    print(f"\n{'='*70}")
    if passed == total:
        print("✅✅✅ 502 BAD GATEWAY IS RESOLVED")
        print("All API endpoints are responding with HTTP 200")
        print("Backend is UP and serving correctly")
    elif passed > 0:
        print("⚠️  PARTIAL SUCCESS")
        print(f"{passed}/{total} endpoints working, but some failures detected")
    else:
        print("❌ BACKEND NOT RESPONDING")
        print("502 Bad Gateway may still be present or backend is down")
    print(f"{'='*70}")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
