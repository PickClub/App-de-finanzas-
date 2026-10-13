"""C3/R9 stage 1: specification model + strict expected failures of real code.

Stdlib only; AST extraction avoids server startup, dotenv and database clients.
Run: python3 -B -m unittest backend.tests.test_history_date_contract -v
"""
import ast
import asyncio
import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo


def actual_functions():
    tree = ast.parse((Path(__file__).parents[1] / "server.py").read_text())
    ns = dict(datetime=datetime, date=date, timedelta=timedelta, timezone=timezone,
              DEFAULT_USER_ID="default-user", PROJ={}, shared_public=lambda value: value)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
            "list_transactions", "summary", "_parse_dt", "_local_tz", "_month_bounds", "_cal_dt"}:
            node.decorator_list = []
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<actual server AST>", "exec"), ns)
    return ns


class Cursor:
    def __init__(self, rows): self.rows = copy.deepcopy(rows)
    def sort(self, key, direction):
        self.rows.sort(key=lambda row: row[key], reverse=direction < 0)
        return self
    async def to_list(self, limit): return self.rows[:limit]
    def __aiter__(self): self.iterator = iter(self.rows); return self
    async def __anext__(self):
        try: return next(self.iterator)
        except StopIteration: raise StopAsyncIteration


class Collection:
    def __init__(self, rows): self.rows = rows
    def find(self, *args, **kwargs): return Cursor(self.rows)


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def key(row): return instant(row["date"]), row["id"]


def specification_page(rows, *, account=None, category=None, types=None,
                       start=None, end=None, after=None, limit=100, order="recent",
                       user="default-user"):
    """Test-only oracle, NOT a proposed production implementation/cursor codec."""
    if not 1 <= limit <= 100 or order not in {"recent", "oldest"}:
        raise ValueError("Invalid page parameters")
    if types and not set(types) <= {"income", "expense", "transfer", "debt_payment", "loan_given", "loan_received"}:
        raise ValueError("Unknown transaction type")
    matched = [r for r in rows
               if r["user_id"] == user
               and (not account or r.get("account_id") == account or
                   r["type"] == "transfer" and r.get("to_account_id") == account)
               and (not category or r.get("category_id") == category)
               and (not types or r["type"] in types)
               and (start is None or instant(r["date"]) >= start)
               and (end is None or instant(r["date"]) < end)
               and (after is None or (key(r) < after if order == "recent" else key(r) > after))]
    ordered = sorted(matched, key=key, reverse=order == "recent")
    page = ordered[:limit]
    return page, key(page[-1]) if len(ordered) > limit else None


def row(i, **fields):
    return dict(id=f"t-{i:06d}", user_id="default-user", date="2026-10-01T12:00:00Z", type="expense",
                account_id="A", category_id="C", amount="1.00", **fields)


class ProposedContract(unittest.TestCase):
    def test_oldest_order_context_category_and_invalid_filters(self):
        rows = [row(i) for i in range(8)]
        rows += [dict(row(90), user_id="other"), dict(row(91), category_id="other")]
        a, cursor = specification_page(rows, category="C", order="oldest", limit=3)
        b, _ = specification_page(rows, category="C", order="oldest", limit=3, after=cursor)
        self.assertEqual([r["id"] for r in a+b], [row(i)["id"] for i in range(6)])
        for options in ({"limit":0}, {"limit":101}, {"types":{"unknown"}}, {"order":"high"}):
            with self.assertRaises(ValueError): specification_page(rows, **options)

    def test_equivalent_offset_instants_use_identifier_tie_breaker(self):
        rows = [dict(row(1), date="2026-10-01T08:00:00-04:00"),
                dict(row(2), date="2026-10-01T12:00:00Z")]
        self.assertEqual(key(rows[0])[0], key(rows[1])[0])
        a, cursor = specification_page(rows, limit=1)
        b, _ = specification_page(rows, limit=1, after=cursor)
        self.assertEqual([a[0]["id"], b[0]["id"]], [row(2)["id"], row(1)["id"]])

    def test_501_2001_10001_complete_tied_pages_and_totals(self):
        for count in (501, 2001, 10001):
            rows = [row(i) for i in range(count)]; original = copy.deepcopy(rows)
            seen, cursor = [], None
            while True:
                page, cursor = specification_page(rows, after=cursor)
                seen.extend(page)
                if cursor is None: break
            self.assertEqual(len(seen), count)
            self.assertEqual(len({r["id"] for r in seen}), count)
            self.assertEqual(seen, sorted(rows, key=key, reverse=True))
            self.assertEqual(sum(Decimal(r["amount"]) for r in seen), Decimal(count))
            self.assertEqual(rows, original)

    def test_filters_before_limit_and_transfer_participation(self):
        rows = [row(i) for i in range(600)]
        incoming = dict(row(900), type="transfer", account_id="B", to_account_id="A")
        outgoing = dict(row(901), type="transfer", to_account_id="B")
        self_transfer = dict(row(902), type="transfer", to_account_id="A")
        invalid_destination = dict(row(903), account_id="B", to_account_id="A")
        rows += [incoming, outgoing, self_transfer, invalid_destination]
        p, _ = specification_page(rows, account="A", category="C", types={"transfer"},
                                  start=instant("2026-10-01T00:00:00Z"), end=instant("2026-10-02T00:00:00Z"))
        self.assertEqual({r["id"] for r in p}, {incoming["id"], outgoing["id"], self_transfer["id"]})
        self.assertEqual(len(p), 3)
        self.assertEqual(specification_page(rows, start=instant("2026-10-01T12:00:00Z"),
                         end=instant("2026-10-01T12:00:00Z"))[0], [])

    def test_live_cursor_insertions_do_not_shift_existing_rows(self):
        rows = [row(i) for i in range(10)]
        first, cursor = specification_page(rows, limit=3)
        rows += [row(20), row(1000)]
        second, _ = specification_page(rows, after=cursor, limit=3)
        self.assertEqual([r["id"] for r in second], [row(i)["id"] for i in (6, 5, 4)])
        self.assertFalse({r["id"] for r in first} & {r["id"] for r in second})

    def test_live_cursor_edits_can_repeat_or_omit_require_refresh(self):
        rows = [row(i) for i in range(10)]
        first, cursor = specification_page(rows, limit=3)
        rows[9]["date"] = "2026-09-01T00:00:00Z"  # already seen, moves after cursor
        rows[0]["date"] = "2026-11-01T00:00:00Z"  # unseen, moves before cursor
        remainder, _ = specification_page(rows, after=cursor, limit=100)
        self.assertIn(row(9)["id"], {r["id"] for r in first} & {r["id"] for r in remainder})
        self.assertNotIn(row(0)["id"], {r["id"] for r in remainder})

    def test_direct_id_and_full_totals_independent_of_pages(self):
        rows = [row(i) for i in range(2001)]
        self.assertEqual(next(r for r in rows if r["id"] == row(0)["id"]), row(0))
        self.assertIsNone(next((r for r in rows if r["id"] == "missing"), None))
        self.assertEqual(sum(Decimal(r["amount"]) for r in rows), Decimal("2001"))
        self.assertEqual(len(specification_page(rows, limit=20)[0]), 20)

    def test_calendar_days_and_iana_month_bounds(self):
        tz = ZoneInfo("America/Chicago")
        for value, expected in [("2026-01-01T05:59:59Z", date(2025, 12, 31)),
                                ("2026-01-01T06:00:00Z", date(2026, 1, 1)),
                                ("2024-03-01T05:59:59Z", date(2024, 2, 29))]:
            self.assertEqual(instant(value).astimezone(tz).date(), expected)
        self.assertEqual((date(2024, 2, 28) + timedelta(days=1)).isoformat(), "2024-02-29")
        with self.assertRaises(ValueError): date.fromisoformat("2026-02-29")
        for month, hours in ((3, 743), (11, 721)):
            a = datetime(2026, month, 1, tzinfo=tz).astimezone(timezone.utc)
            b = datetime(2026, month+1, 1, tzinfo=tz).astimezone(timezone.utc)
            self.assertEqual((b-a).total_seconds()/3600, hours)

    def test_legacy_parse_and_all_day_calendar_unchanged(self):
        ns = actual_functions(); tz = ZoneInfo("America/Chicago")
        self.assertEqual(ns["_parse_dt"]("2026-01-01T00:00:00").tzinfo, timezone.utc)
        self.assertEqual(ns["_cal_dt"]("2026-01-01", tz), (date(2026, 1, 1), None))
        self.assertEqual(ns["_cal_dt"]("2026-01-01T05:00:00Z", tz), (date(2025, 12, 31), "23:00"))

    def test_dst_gaps_and_repeated_hour_remain_distinct_instants(self):
        tz = ZoneInfo("America/Chicago")
        before = instant("2026-03-08T07:59:59Z").astimezone(tz)
        after = instant("2026-03-08T08:00:00Z").astimezone(tz)
        self.assertEqual((before.hour, after.hour), (1, 3))
        first = instant("2026-11-01T06:30:00Z").astimezone(tz)
        second = instant("2026-11-01T07:30:00Z").astimezone(tz)
        self.assertEqual((first.hour, second.hour), (1, 1))
        self.assertNotEqual(first.utcoffset(), second.utcoffset())
        self.assertEqual((second.astimezone(timezone.utc)-first.astimezone(timezone.utc)).total_seconds(), 3600)


class CurrentDefects(unittest.TestCase):
    def setUp(self):
        # unittest does not apply expectedFailure to setUp. Extraction/runtime
        # errors therefore fail CI instead of masquerading as known defects.
        ns = actual_functions()
        if self._testMethodName == "test_account_history_must_not_be_truncated_before_filter":
            rows = [row(i) for i in range(501)]
            rows[0]["date"] = "2020-01-01T00:00:00Z"; rows[0]["account_id"] = "target"
            ns["db"] = SimpleNamespace(transactions=Collection(rows))
            returned = asyncio.run(ns["list_transactions"]())
            self.observed = len([r for r in returned if r["account_id"] == "target"])
            self.required = 1
        elif self._testMethodName == "test_summary_must_include_current_expense_after_2000":
            rows = [dict(row(i), date="2000-01-01T00:00:00Z", amount=1) for i in range(2000)]
            rows.append(dict(row(2001), date=datetime.now(timezone.utc).isoformat(), amount=70))
            ns["db"] = SimpleNamespace(transactions=Collection(rows), accounts=Collection([]),
                                       debts=Collection([]), debt_payments=Collection([]))
            self.observed = asyncio.run(ns["summary"]())["month_expense"]
            self.required = 70
        else:
            start, _ = ns["_month_bounds"](2026, 3, ns["_local_tz"](300))
            self.observed = start.astimezone(timezone.utc)
            self.required = datetime(2026, 3, 1, tzinfo=ZoneInfo("America/Chicago")).astimezone(timezone.utc)

    @unittest.expectedFailure
    def test_account_history_must_not_be_truncated_before_filter(self):
        self.assertEqual(self.observed, self.required)

    @unittest.expectedFailure
    def test_summary_must_include_current_expense_after_2000(self):
        self.assertEqual(self.observed, self.required)

    @unittest.expectedFailure
    def test_current_offset_cannot_replace_iana_historical_rules(self):
        self.assertEqual(self.observed, self.required)


if __name__ == "__main__": unittest.main()
