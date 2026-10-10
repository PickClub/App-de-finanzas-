#!/usr/bin/env python3
"""
Financial Calendar API Testing
Tests the read-only calendar aggregation endpoints against isolated instance at http://127.0.0.1:8011/api
System date: 2026-10-10
Test data seeded by /tmp/cal_seed.py
"""

import json
import urllib.request
import urllib.error
from datetime import date, datetime
from decimal import Decimal

# Test configuration
BASE_URL = "http://127.0.0.1:8011/api"
PROD_URL = "http://127.0.0.1:8001/api"

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def success(self, msg):
        self.passed += 1
        print(f"  ✅ {msg}")
    
    def fail(self, msg):
        self.failed += 1
        self.errors.append(msg)
        print(f"  ❌ {msg}")
    
    def summary(self):
        total = self.passed + self.failed
        pct = (self.passed / total * 100) if total > 0 else 0
        print(f"\n{'='*80}")
        print(f"SUMMARY: {self.passed}/{total} tests passed ({pct:.1f}%)")
        if self.errors:
            print(f"\nFAILURES ({len(self.errors)}):")
            for i, err in enumerate(self.errors, 1):
                print(f"  {i}. {err}")
        print(f"{'='*80}\n")
        return self.passed, self.failed

result = TestResult()

def req(method, path, body=None, headers=None, base=BASE_URL, expect_error=None):
    """Make HTTP request"""
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", **(headers or {})}
    r = urllib.request.Request(url, method=method, data=data, headers=headers)
    
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        if expect_error and e.code == expect_error:
            return {"error": e.read().decode()}, e.code
        raise Exception(f"{method} {path} -> {e.code}: {e.read().decode()[:500]}")

def get(path, base=BASE_URL, expect_error=None):
    """GET request"""
    return req("GET", path, base=base, expect_error=expect_error)

def post(path, body, base=BASE_URL):
    """POST request"""
    return req("POST", path, body, base=base)

def check_event(event, expected):
    """Check if event matches expected fields"""
    for key, val in expected.items():
        if key not in event:
            return False, f"Missing field '{key}'"
        if event[key] != val:
            return False, f"Field '{key}': expected {val}, got {event[key]}"
    return True, None

def find_event(events, **criteria):
    """Find event matching criteria"""
    for e in events:
        match = all(e.get(k) == v for k, v in criteria.items())
        if match:
            return e
    return None

print("="*80)
print("FINANCIAL CALENDAR API TESTING")
print("="*80)
print(f"Isolated instance: {BASE_URL}")
print(f"Production instance: {PROD_URL}")
print(f"System date: 2026-10-10")
print("="*80)

# ============================================================================
# TEST 1: GET /calendar/events - Main range with all expected events
# ============================================================================
print("\n[TEST 1] GET /calendar/events?start=2026-09-28&end=2026-11-08 (tz_offset=0)")

resp, status = get("/calendar/events?start=2026-09-28&end=2026-11-08&tz_offset=0")
if status != 200:
    result.fail(f"Expected 200, got {status}")
else:
    result.success(f"HTTP 200")
    
    events = resp.get("events", [])
    result.success(f"Returned {len(events)} events")
    
    # Check response structure
    if resp.get("start") == "2026-09-28" and resp.get("end") == "2026-11-08":
        result.success("start/end dates correct")
    else:
        result.fail(f"start/end dates incorrect: {resp.get('start')}, {resp.get('end')}")
    
    if resp.get("today") == "2026-10-10":
        result.success("today date correct")
    else:
        result.fail(f"today date incorrect: {resp.get('today')}")
    
    # 10-01: debt_due "Deuda vencida" overdue
    e = find_event(events, date="2026-10-01", subtype="debt_due", title="Deuda vencida")
    if e:
        if e.get("status") == "overdue" and e.get("sign") == -1 and e.get("realized") == False:
            result.success("10-01 debt_due 'Deuda vencida' overdue found")
        else:
            result.fail(f"10-01 debt_due status/sign incorrect: {e}")
    else:
        result.fail("10-01 debt_due 'Deuda vencida' NOT found")
    
    # 10-05: expense Supermercado (date-only, time=null)
    e = find_event(events, date="2026-10-05", subtype="expense", title="Supermercado")
    if e:
        if e.get("time") is None and e.get("amount") == 80 and e.get("realized") == True:
            result.success("10-05 expense 'Supermercado' date-only (time=null) found")
        else:
            result.fail(f"10-05 expense time/amount incorrect: time={e.get('time')}, amount={e.get('amount')}")
    else:
        result.fail("10-05 expense 'Supermercado' NOT found")
    
    # 10-07 09:30: debt_payment
    e = find_event(events, date="2026-10-07", subtype="debt_payment")
    if e:
        if e.get("time") == "09:30" and e.get("amount") == 100 and e.get("sign") == -1:
            result.success("10-07 09:30 debt_payment found")
        else:
            result.fail(f"10-07 debt_payment time/amount/sign incorrect: {e}")
    else:
        result.fail("10-07 09:30 debt_payment NOT found")
    
    # 10-09 18:00: recurring_paid "Factura de agua"
    e = find_event(events, date="2026-10-09", subtype="recurring_paid", title="Factura de agua")
    if e:
        if e.get("time") == "18:00" and e.get("amount") == 45:
            result.success("10-09 18:00 recurring_paid 'Factura de agua' found")
        else:
            result.fail(f"10-09 recurring_paid time/amount incorrect: {e}")
    else:
        result.fail("10-09 18:00 recurring_paid 'Factura de agua' NOT found")
    
    # 10-15: NO recurring_due for water bill (paid by movement, no double count)
    e = find_event(events, date="2026-10-15", subtype="recurring_due", title="Factura de agua")
    if e:
        result.fail("10-15 recurring_due 'Factura de agua' found (SHOULD NOT EXIST - double count)")
    else:
        result.success("10-15 recurring_due 'Factura de agua' NOT found (correct, no double count)")
    
    # 10-10: income 500 at 08:00
    e = find_event(events, date="2026-10-10", subtype="income", title="Ingreso quincenal")
    if e:
        if e.get("time") == "08:00" and e.get("amount") == 500 and e.get("sign") == 1:
            result.success("10-10 08:00 income 500 found")
        else:
            result.fail(f"10-10 income time/amount/sign incorrect: {e}")
    else:
        result.fail("10-10 08:00 income NOT found")
    
    # 10-10: expense 65 at 10:00
    e = find_event(events, date="2026-10-10", subtype="expense", title="Servicio de internet")
    if e:
        if e.get("time") == "10:00" and e.get("amount") == 65 and e.get("sign") == -1:
            result.success("10-10 10:00 expense 65 found")
        else:
            result.fail(f"10-10 expense time/amount/sign incorrect: {e}")
    else:
        result.fail("10-10 10:00 expense NOT found")
    
    # 10-10: transfer 100 (kind=other, sign=0, counts_in_net=false)
    e = find_event(events, date="2026-10-10", subtype="transfer")
    if e:
        if e.get("amount") == 100 and e.get("sign") == 0 and e.get("counts_in_net") == False:
            result.success("10-10 transfer 100 (sign=0, counts_in_net=false) found")
        else:
            result.fail(f"10-10 transfer sign/counts_in_net incorrect: {e}")
    else:
        result.fail("10-10 transfer NOT found")
    
    # 10-10: recurring_due Gimnasio pending (realized=false)
    e = find_event(events, date="2026-10-10", subtype="recurring_due", title="Gimnasio")
    if e:
        if e.get("status") == "pending" and e.get("amount") == 35 and e.get("realized") == False:
            result.success("10-10 recurring_due 'Gimnasio' pending found")
        else:
            result.fail(f"10-10 recurring_due status/amount/realized incorrect: {e}")
    else:
        result.fail("10-10 recurring_due 'Gimnasio' NOT found")
    
    # 10-12: goal_deposit (sign=0, not counted)
    e = find_event(events, date="2026-10-12", subtype="goal_deposit")
    if e:
        if e.get("sign") == 0 and e.get("counts_in_net") == False:
            result.success("10-12 goal_deposit (sign=0, not counted) found")
        else:
            result.fail(f"10-12 goal_deposit sign/counts_in_net incorrect: {e}")
    else:
        result.fail("10-12 goal_deposit NOT found")
    
    # 10-20: recurring_marked Streaming (sign=0)
    e = find_event(events, date="2026-10-20", subtype="recurring_marked", title="Streaming")
    if e:
        if e.get("sign") == 0 and e.get("status") == "marked":
            result.success("10-20 recurring_marked 'Streaming' (sign=0) found")
        else:
            result.fail(f"10-20 recurring_marked sign/status incorrect: {e}")
    else:
        result.fail("10-20 recurring_marked 'Streaming' NOT found")
    
    # 10-22: debt_due 400 (remaining after 100 payment)
    e = find_event(events, date="2026-10-22", subtype="debt_due")
    if e:
        if e.get("amount") == 400 and e.get("sign") == -1:
            result.success("10-22 debt_due 400 (remaining) found")
        else:
            result.fail(f"10-22 debt_due amount/sign incorrect: {e}")
    else:
        result.fail("10-22 debt_due NOT found")
    
    # 10-28: debt_due_collect +200 (they_owe)
    e = find_event(events, date="2026-10-28", subtype="debt_due_collect")
    if e:
        if e.get("amount") == 200 and e.get("sign") == 1:
            result.success("10-28 debt_due_collect +200 found")
        else:
            result.fail(f"10-28 debt_due_collect amount/sign incorrect: {e}")
    else:
        result.fail("10-28 debt_due_collect NOT found")
    
    # 10-30: goal_target
    e = find_event(events, date="2026-10-30", subtype="goal_target")
    if e:
        if e.get("amount") == 950:  # target 1000 - saved 50
            result.success("10-30 goal_target 950 found")
        else:
            result.fail(f"10-30 goal_target amount incorrect: expected 950, got {e.get('amount')}")
    else:
        result.fail("10-30 goal_target NOT found")
    
    # Paused "Revista pausada" must produce NO events
    e = find_event(events, title="Revista pausada")
    if e:
        result.fail("Paused 'Revista pausada' found (SHOULD NOT EXIST)")
    else:
        result.success("Paused 'Revista pausada' NOT found (correct)")
    
    # Check ref_id exists on all events
    all_have_ref = all("ref_id" in e for e in events)
    if all_have_ref:
        result.success("All events have ref_id")
    else:
        result.fail("Some events missing ref_id")

# ============================================================================
# TEST 2: Types filter
# ============================================================================
print("\n[TEST 2] Types filter")

# Valid types filter
resp, status = get("/calendar/events?start=2026-10-01&end=2026-10-31&types=debt,goal")
if status == 200:
    events = resp.get("events", [])
    kinds = set(e["kind"] for e in events)
    if kinds <= {"debt", "goal"}:
        result.success(f"types=debt,goal filter works ({len(events)} events, kinds: {kinds})")
    else:
        result.fail(f"types filter returned wrong kinds: {kinds}")
else:
    result.fail(f"types filter failed: {status}")

# Invalid type
resp, status = get("/calendar/events?start=2026-10-01&end=2026-10-31&types=invalid", expect_error=422)
if status == 422:
    result.success("Invalid type returns 422")
else:
    result.fail(f"Invalid type should return 422, got {status}")

# ============================================================================
# TEST 3: Validation errors
# ============================================================================
print("\n[TEST 3] Validation errors")

# end < start
resp, status = get("/calendar/events?start=2026-10-31&end=2026-10-01", expect_error=422)
if status == 422:
    result.success("end < start returns 422")
else:
    result.fail(f"end < start should return 422, got {status}")

# range > 400 days
resp, status = get("/calendar/events?start=2026-01-01&end=2027-12-31", expect_error=422)
if status == 422:
    result.success("range > 400 days returns 422")
else:
    result.fail(f"range > 400 days should return 422, got {status}")

# invalid date
resp, status = get("/calendar/events?start=2026-13-45&end=2026-10-31", expect_error=422)
if status == 422:
    result.success("Invalid date returns 422")
else:
    result.fail(f"Invalid date should return 422, got {status}")

# ============================================================================
# TEST 4: tz_offset
# ============================================================================
print("\n[TEST 4] tz_offset")

# Create a transaction at 2026-10-10T02:00Z (UTC)
# With tz_offset=300 (UTC-5), this is 2026-10-09 21:00 local
acc_resp, _ = get("/accounts")
if acc_resp and len(acc_resp) > 0:
    acc_id = acc_resp[0]["id"]
    cat_resp, _ = get("/categories")
    if cat_resp and len(cat_resp) > 0:
        cat_id = next((c["id"] for c in cat_resp if c.get("type") == "expense"), None)
        if cat_id:
            tx_body = {
                "name": "Test TZ",
                "amount": 25,
                "type": "expense",
                "date": "2026-10-10T02:00:00+00:00",
                "account_id": acc_id,
                "category_id": cat_id
            }
            tx_resp, _ = post("/transactions", tx_body)
            tx_id = tx_resp.get("id")
            
            # Query with tz_offset=300 (UTC-5)
            resp, status = get("/calendar/events?start=2026-10-09&end=2026-10-10&tz_offset=300")
            if status == 200:
                events = resp.get("events", [])
                e = find_event(events, date="2026-10-09", title="Test TZ")
                if e and e.get("time") == "21:00":
                    result.success("tz_offset=300: 2026-10-10T02:00Z appears on 10-09 at 21:00")
                else:
                    result.fail(f"tz_offset=300: event not found or time incorrect: {e}")
            else:
                result.fail(f"tz_offset query failed: {status}")
            
            # Cleanup
            req("DELETE", f"/transactions/{tx_id}")
        else:
            result.fail("No expense category found for tz_offset test")
    else:
        result.fail("No categories found for tz_offset test")
else:
    result.fail("No accounts found for tz_offset test")

# ============================================================================
# TEST 5: GET /calendar/summary?year=2026&month=10
# ============================================================================
print("\n[TEST 5] GET /calendar/summary?year=2026&month=10")

resp, status = get("/calendar/summary?year=2026&month=10")
if status != 200:
    result.fail(f"Expected 200, got {status}")
else:
    result.success("HTTP 200")
    
    # Check structure
    if resp.get("year") == 2026 and resp.get("month") == 10:
        result.success("year/month correct")
    else:
        result.fail(f"year/month incorrect: {resp.get('year')}, {resp.get('month')}")
    
    # income: 500/1 (Ingreso quincenal)
    income = resp.get("income", {})
    if income.get("amount") == 500 and income.get("count") == 1:
        result.success(f"income: 500/1 ✓")
    else:
        result.fail(f"income incorrect: expected 500/1, got {income.get('amount')}/{income.get('count')}")
    
    # payments: 290/4 (expense 80+65+45 + debt payment 100)
    # Note: transfer and goal contribution excluded
    payments = resp.get("payments", {})
    expected_payments = 80 + 65 + 45 + 100  # 290
    if payments.get("amount") == expected_payments and payments.get("count") == 4:
        result.success(f"payments: 290/4 (expense 80+65+45 + debt payment 100) ✓")
    else:
        result.fail(f"payments incorrect: expected 290/4, got {payments.get('amount')}/{payments.get('count')}")
    
    # bills: 0/0, available=false
    bills = resp.get("bills", {})
    if bills.get("amount") == 0 and bills.get("count") == 0 and bills.get("available") == False:
        result.success("bills: 0/0, available=false ✓")
    else:
        result.fail(f"bills incorrect: {bills}")
    
    # planned_expenses: 485/3 (Gimnasio 35 + debt_due 400 + debt_due 50)
    planned_exp = resp.get("planned_expenses", {})
    expected_planned_exp = 35 + 400 + 50  # 485
    if planned_exp.get("amount") == expected_planned_exp and planned_exp.get("count") == 3:
        result.success(f"planned_expenses: 485/3 ✓")
    else:
        result.fail(f"planned_expenses incorrect: expected 485/3, got {planned_exp.get('amount')}/{planned_exp.get('count')}")
    
    # planned_income: 200/1 (debt_due_collect)
    planned_inc = resp.get("planned_income", {})
    if planned_inc.get("amount") == 200 and planned_inc.get("count") == 1:
        result.success(f"planned_income: 200/1 ✓")
    else:
        result.fail(f"planned_income incorrect: expected 200/1, got {planned_inc.get('amount')}/{planned_inc.get('count')}")
    
    # net_real: 210 (income 500 - expenses 80+65+45 - debt_payment 100)
    net_real = resp.get("net_real")
    expected_net = 500 - 80 - 65 - 45 - 100  # 210
    if net_real == expected_net:
        result.success(f"net_real: 210 ✓")
    else:
        result.fail(f"net_real incorrect: expected 210, got {net_real}")

# ============================================================================
# TEST 6: GET /calendar/upcoming
# ============================================================================
print("\n[TEST 6] GET /calendar/upcoming?limit=3")

resp, status = get("/calendar/upcoming?limit=3")
if status != 200:
    result.fail(f"Expected 200, got {status}")
else:
    result.success("HTTP 200")
    
    items = resp.get("items", [])
    total = resp.get("total", 0)
    has_more = resp.get("has_more", False)
    
    if len(items) <= 3:
        result.success(f"limit=3 respected ({len(items)} items)")
    else:
        result.fail(f"limit=3 not respected: got {len(items)} items")
    
    if "total" in resp and "has_more" in resp:
        result.success(f"Pagination fields present (total={total}, has_more={has_more})")
    else:
        result.fail("Pagination fields missing")
    
    # Check that items have days_left
    if all("days_left" in item for item in items):
        result.success("All items have days_left")
    else:
        result.fail("Some items missing days_left")
    
    # Check that overdue items have negative days_left
    overdue = [item for item in items if item.get("status") == "overdue"]
    if all(item.get("days_left", 0) < 0 for item in overdue):
        result.success(f"Overdue items have negative days_left ({len(overdue)} overdue)")
    else:
        result.fail("Some overdue items have non-negative days_left")
    
    # Check that realized items are excluded
    realized = [item for item in items if item.get("realized") == True]
    if len(realized) == 0:
        result.success("Realized items excluded")
    else:
        result.fail(f"Realized items found: {len(realized)}")
    
    # Check that paused recurrences are excluded
    paused = [item for item in items if "Revista pausada" in item.get("title", "")]
    if len(paused) == 0:
        result.success("Paused recurrences excluded")
    else:
        result.fail(f"Paused recurrences found: {len(paused)}")

# Test offset pagination
resp2, status2 = get("/calendar/upcoming?limit=3&offset=3")
if status2 == 200:
    items2 = resp2.get("items", [])
    if resp2.get("offset") == 3:
        result.success("Offset pagination works")
    else:
        result.fail(f"Offset incorrect: expected 3, got {resp2.get('offset')}")
else:
    result.fail(f"Offset pagination failed: {status2}")

# ============================================================================
# TEST 7: Recurring payment ended produces no future dues
# ============================================================================
print("\n[TEST 7] Recurring payment ended produces no future dues")

# Get recurring payments
rp_resp, _ = get("/recurring-payments")
if rp_resp and len(rp_resp) > 0:
    # Find Gimnasio (active)
    gimnasio = next((r for r in rp_resp if r.get("name") == "Gimnasio"), None)
    if gimnasio:
        rp_id = gimnasio["id"]
        
        # End the recurring payment
        end_resp, end_status = post(f"/recurring-payments/{rp_id}/end", {})
        if end_status == 200:
            result.success("Ended recurring payment 'Gimnasio'")
            
            # Query future events (November)
            resp, status = get("/calendar/events?start=2026-11-01&end=2026-11-30")
            if status == 200:
                events = resp.get("events", [])
                gimnasio_events = [e for e in events if "Gimnasio" in e.get("title", "")]
                if len(gimnasio_events) == 0:
                    result.success("No future dues for ended recurring payment")
                else:
                    result.fail(f"Found {len(gimnasio_events)} future dues for ended recurring payment")
            else:
                result.fail(f"Query future events failed: {status}")
        else:
            result.fail(f"Failed to end recurring payment: {end_status}")
    else:
        result.fail("Gimnasio recurring payment not found")
else:
    result.fail("No recurring payments found")

# ============================================================================
# TEST 8: Partial payment on recurring due
# ============================================================================
print("\n[TEST 8] Partial payment on recurring due")

# Get recurring payments
rp_resp, _ = get("/recurring-payments")
if rp_resp and len(rp_resp) > 0:
    # Find Gimnasio (should be ended from previous test, so skip or use another)
    # Let's create a new one for this test
    acc_resp, _ = get("/accounts")
    cat_resp, _ = get("/categories")
    if acc_resp and cat_resp:
        acc_id = acc_resp[0]["id"]
        cat_id = next((c["id"] for c in cat_resp if c.get("type") == "expense"), None)
        
        if acc_id and cat_id:
            # Create new recurring payment
            rp_body = {
                "name": "Test Partial",
                "amount": 35,
                "frequency": "monthly",
                "start_date": "2026-11-10",
                "category_id": cat_id,
                "account_id": acc_id
            }
            rp_resp, _ = post("/recurring-payments", rp_body)
            rp_id = rp_resp.get("id")
            
            # Make partial payment (20 of 35)
            payment_body = {
                "due_date": "2026-11-10",
                "mode": "expense",
                "amount": 20,
                "account_id": acc_id,
                "date": "2026-11-10T10:00:00+00:00"
            }
            payment_resp, _ = post(f"/recurring-payments/{rp_id}/payments", payment_body)
            
            # Query events for November
            resp, status = get("/calendar/events?start=2026-11-01&end=2026-11-30")
            if status == 200:
                events = resp.get("events", [])
                
                # Should have recurring_paid for 20
                paid_event = find_event(events, date="2026-11-10", subtype="recurring_paid", title="Test Partial")
                if paid_event and paid_event.get("amount") == 20:
                    result.success("Partial payment: recurring_paid 20 found")
                else:
                    result.fail(f"Partial payment: recurring_paid 20 not found or incorrect: {paid_event}")
                
                # Should have recurring_due for remaining 15 with partial=true
                due_event = find_event(events, date="2026-11-10", subtype="recurring_due", title="Test Partial")
                if due_event:
                    if due_event.get("amount") == 15 and due_event.get("partial") == True:
                        result.success("Partial payment: recurring_due 15 with partial=true found")
                    else:
                        result.fail(f"Partial payment: recurring_due incorrect: amount={due_event.get('amount')}, partial={due_event.get('partial')}")
                else:
                    result.fail("Partial payment: recurring_due for remaining 15 not found")
                
                # Verify no double count (should have both events, not just one)
                test_partial_events = [e for e in events if "Test Partial" in e.get("title", "")]
                if len(test_partial_events) == 2:
                    result.success("Partial payment: both events present (no double count)")
                else:
                    result.fail(f"Partial payment: expected 2 events, got {len(test_partial_events)}")
            else:
                result.fail(f"Query events failed: {status}")
            
            # Cleanup
            req("DELETE", f"/recurring-payments/{rp_id}")
        else:
            result.fail("No account or category found for partial payment test")
    else:
        result.fail("No accounts or categories found for partial payment test")
else:
    result.fail("No recurring payments found for partial payment test")

# ============================================================================
# TEST 9: Leap year February 2028
# ============================================================================
print("\n[TEST 9] Leap year February 2028")

# Query Feb 2028 (leap year)
resp, status = get("/calendar/events?start=2028-02-01&end=2028-02-29")
if status == 200:
    result.success("Feb 2028 (leap year) range 2028-02-01..2028-02-29 returns 200")
else:
    result.fail(f"Feb 2028 query failed: {status}")

# Create a recurring payment with due_day=31 (should clamp to Feb 29)
acc_resp, _ = get("/accounts")
cat_resp, _ = get("/categories")
if acc_resp and cat_resp:
    acc_id = acc_resp[0]["id"]
    cat_id = next((c["id"] for c in cat_resp if c.get("type") == "expense"), None)
    
    if acc_id and cat_id:
        rp_body = {
            "name": "Test Leap Year",
            "amount": 50,
            "frequency": "monthly",
            "start_date": "2028-01-31",
            "due_day": 31,
            "category_id": cat_id,
            "account_id": acc_id
        }
        rp_resp, _ = post("/recurring-payments", rp_body)
        rp_id = rp_resp.get("id")
        
        # Query Feb 2028
        resp, status = get("/calendar/events?start=2028-02-01&end=2028-02-29")
        if status == 200:
            events = resp.get("events", [])
            # Should have event on Feb 29 (clamped from day 31)
            feb_event = find_event(events, date="2028-02-29", title="Test Leap Year")
            if feb_event:
                result.success("Recurring monthly due_day 31 clamped to 2028-02-29")
            else:
                result.fail("Recurring monthly due_day 31 NOT clamped to 2028-02-29")
        else:
            result.fail(f"Feb 2028 query failed: {status}")
        
        # Cleanup
        req("DELETE", f"/recurring-payments/{rp_id}")
    else:
        result.fail("No account or category found for leap year test")
else:
    result.fail("No accounts or categories found for leap year test")

# ============================================================================
# TEST 10: Account balances unchanged by calendar calls
# ============================================================================
print("\n[TEST 10] Account balances unchanged by calendar calls")

# Get accounts before
acc_before, _ = get("/accounts")
balances_before = {a["id"]: a.get("current_balance") for a in acc_before}

# Make several calendar calls
get("/calendar/events?start=2026-10-01&end=2026-10-31")
get("/calendar/summary?year=2026&month=10")
get("/calendar/upcoming?limit=10")

# Get accounts after
acc_after, _ = get("/accounts")
balances_after = {a["id"]: a.get("current_balance") for a in acc_after}

if balances_before == balances_after:
    result.success("Account balances unchanged by calendar calls")
else:
    result.fail(f"Account balances changed: before={balances_before}, after={balances_after}")

# ============================================================================
# TEST 11: Read-only GET on production backend (port 8001)
# ============================================================================
print("\n[TEST 11] Read-only GET on production backend (port 8001)")

resp, status = get("/calendar/summary?year=2026&month=10", base=PROD_URL)
if status == 200:
    result.success("GET /calendar/summary on port 8001 returns 200")
else:
    result.fail(f"GET /calendar/summary on port 8001 failed: {status}")

# ============================================================================
# SUMMARY
# ============================================================================
passed, failed = result.summary()

# Exit with appropriate code
import sys
sys.exit(0 if failed == 0 else 1)
