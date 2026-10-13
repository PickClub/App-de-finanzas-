"""C3 stage 2: real route AST + production reader, only synthetic memory.

No server import, MongoDB client, dotenv, startup, financial writes or indexes.
"""
import ast
import base64
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, List, Literal, Optional
import unittest

from fastapi import APIRouter, FastAPI, Query
import httpx
from pymongo.errors import OperationFailure
from backend.transaction_history import read_page, read_detail
from backend.shared_obligations import public_financial_document


def matches(row, query):
    for k, v in query.items():
        if k == "$or":
            if not any(matches(row, part) for part in v): return False
        elif isinstance(v, dict):
            if "$in" in v and row.get(k) not in v["$in"]: return False
        elif row.get(k) != v: return False
    return True


class Cursor:
    def __init__(self, rows): self.rows = copy.deepcopy(rows)
    def sort(self, field, direction):
        self.rows.sort(key=lambda r:r[field], reverse=direction < 0); return self
    async def to_list(self, limit): return self.rows[:limit]
    def __aiter__(self): self.iterator = iter(self.rows); return self
    async def __anext__(self):
        try: return next(self.iterator)
        except StopIteration: raise StopAsyncIteration


class Collection:
    def __init__(self): self.rows = []; self.fail = False; self.queries = []
    def find(self, query, projection):
        self.queries.append(copy.deepcopy(query))
        if self.fail: raise OperationFailure("synthetic read failure")
        return Cursor([r for r in self.rows if matches(r, query)])
    # No mutation methods: an accidental write fails immediately.


def row(i, **changes):
    return dict(dict(id=f"t-{i:06d}", user_id="default-user", date="2026-10-01T12:00:00Z",
                     amount=70, type="expense", account_id="A", category_id="C"), **changes)


class TransactionHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.collection = Collection()
        self.settings = SimpleNamespace(mongo_url="mongodb://synthetic.invalid", db_name="synthetic",
                                        expected_financial_environment_id=None)
        self.ns = dict(api=APIRouter(prefix="/api"), db=SimpleNamespace(transactions=self.collection),
                       settings=self.settings, DEFAULT_USER_ID="default-user", PROJ={"_id":0},
                       shared_public=public_financial_document, Query=Query, Annotated=Annotated,
                       Optional=Optional, List=List, Literal=Literal,
                       read_transaction_page=read_page, read_transaction_detail=read_detail)
        tree = ast.parse((Path(__file__).parents[1]/"server.py").read_text())
        wanted = {"transaction_page", "get_transaction", "list_transactions"}
        nodes = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name in wanted]
        self.assertEqual({n.name for n in nodes}, wanted)
        exec(compile(ast.Module(body=nodes,type_ignores=[]), "<actual history routes>", "exec"), self.ns)
        self.app = FastAPI(); self.app.include_router(self.ns["api"])

    async def request(self, path="/transactions/page", params=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://synthetic.invalid") as client:
            return await client.get("/api"+path, params=params)

    async def page(self, params=None):
        response = await self.request(params=params)
        self.assertEqual(response.status_code,200,response.text)
        result = response.json()
        self.assertEqual(set(result), {"items","has_more","next_cursor"})
        self.assertEqual(result["has_more"], result["next_cursor"] is not None)
        return result

    async def test_complete_history_501_2001_10001_and_unchanged_documents(self):
        for count in (501,2001,10001):
            self.collection.rows = [row(i) for i in range(count)]
            original = copy.deepcopy(self.collection.rows); ids=[]; params={"limit":100}
            while True:
                result=await self.page(params);ids.extend(r["id"] for r in result["items"])
                if not result["has_more"]:break
                params["cursor"]=result["next_cursor"]
            self.assertEqual(ids, sorted([r["id"] for r in original],reverse=True))
            self.assertEqual(len(set(ids)), count)
            self.assertEqual(self.collection.rows,original)

    async def test_filters_before_limit_and_transfer_extremes(self):
        self.collection.rows=[row(i,account_id="B") for i in range(2001)] + [
            row(3000), row(3001,type="transfer",to_account_id="B"),
            row(3002,type="transfer",account_id="B",to_account_id="A"),
            row(3003,type="transfer",to_account_id="A"),
            row(3004,account_id="B",to_account_id="A"),row(3005,category_id="other"),
            row(3006,date="2026-10-02T00:00:00Z"),row(3007,user_id="other")]
        params=[("account_id","A"),("category_id","C"),("type","expense"),("type","transfer"),
                ("start","2026-10-01T00:00:00Z"),("end","2026-10-02T00:00:00Z"),("limit","10")]
        result=await self.page(params)
        self.assertEqual({r["id"] for r in result["items"]},{row(i)["id"] for i in range(3000,3004)})
        self.assertIn("$or",self.collection.queries[-1]);self.assertIn("$in",self.collection.queries[-1]["type"])

    async def test_offsets_microseconds_naive_and_date_only_without_rewriting(self):
        self.collection.rows=[row(1,date="2026-10-01T08:00:00.000001-04:00"),
                              row(2,date="2026-10-01T12:00:00.000001Z"),
                              row(3,date="2026-10-01T12:00:00.000002"),row(4,date="2026-10-01")]
        for order, expected in (("recent",[3,2,1,4]),("oldest",[4,1,2,3])):
            ids=[];p={"order":order,"limit":1}
            while True:
                result=await self.page(p);ids.extend(r["id"] for r in result["items"])
                if not result["has_more"]:break
                p["cursor"]=result["next_cursor"]
            self.assertEqual(ids,[row(i)["id"] for i in expected])
        self.assertEqual(self.collection.rows[0]["date"],"2026-10-01T08:00:00.000001-04:00")

    async def test_invalid_parameters_and_cursors(self):
        self.collection.rows=[row(i) for i in range(3)]
        for params in ({"limit":0},{"limit":101},{"limit":"x"},{"order":"high"},
                       {"type":"unknown"},{"account_id":""},{"category_id":" "},
                       {"start":"2026-01-01"},{"start":"2026-01-01T00:00:00"},
                       {"start":"bad"},{"start":"2026-02-01T00:00:00Z","end":"2026-01-01T00:00:00Z"},
                       {"cursor":"!"},{"cursor":""},{"cursor":"a"},{"cursor":"e30"},{"cursor":"a"*2049}):
            response=await self.request(params=params);self.assertEqual(response.status_code,422,response.text)

    async def test_cursor_bound_to_filters_user_context_order_not_page_size(self):
        self.collection.rows=[row(i) for i in range(4)]
        token=(await self.page({"limit":1}))["next_cursor"]
        for extra in ({"order":"oldest"},{"type":"expense"},{"account_id":"A"},
                      {"category_id":"C"},{"start":"2026-01-01T00:00:00Z"}):
            self.assertEqual((await self.request(params=dict(extra,cursor=token))).status_code,422)
        self.settings.db_name="different"
        self.assertEqual((await self.request(params={"cursor":token})).status_code,422)
        self.settings.db_name="synthetic";self.ns["DEFAULT_USER_ID"]="other"
        self.assertEqual((await self.request(params={"cursor":token})).status_code,422)
        self.ns["DEFAULT_USER_ID"]="default-user"
        result=await self.page({"cursor":token,"limit":2})
        self.assertEqual(len(result["items"]),2)
        decoded=json.loads(base64.urlsafe_b64decode(token+"="*(-len(token)%4)))
        self.assertNotIn("synthetic.invalid",json.dumps(decoded))

    async def test_empty_page_and_equal_window(self):
        self.assertEqual((await self.page())["items"],[])
        self.collection.rows=[row(1)]
        self.assertEqual((await self.page({"start":"2026-10-01T12:00:00Z","end":"2026-10-01T12:00:00Z"}))["items"],[])

    async def test_six_types_and_distinct_equal_amount_intentions(self):
        types=["income","expense","transfer","debt_payment","loan_given","loan_received"]
        self.collection.rows=[row(i,type=kind) for i,kind in enumerate(types)]
        self.collection.rows.append(row(100,type="expense"))
        for kind in types:
            result=await self.page({"type":kind})
            self.assertTrue(all(r["type"]==kind for r in result["items"]))
            self.assertEqual(len(result["items"]),2 if kind=="expense" else 1)

    async def test_valid_shape_tampered_cursor_and_canonical_equivalent_filters(self):
        self.collection.rows=[row(i) for i in range(4)]
        token=(await self.page({"limit":1,"start":"2026-10-01T08:00:00-04:00"}))["next_cursor"]
        result=await self.page({"limit":1,"cursor":token,"start":"2026-10-01T12:00:00Z"})
        self.assertEqual(result["items"][0]["id"],row(2)["id"])
        value=json.loads(base64.urlsafe_b64decode(token+"="*(-len(token)%4)))
        for changed in (dict(value,v=True),dict(value,scope="other"),dict(value,id=None),
                        dict(value,date="bad"),dict(value,unexpected=1)):
            bad=base64.urlsafe_b64encode(json.dumps(changed).encode()).decode().rstrip("=")
            self.assertEqual((await self.request(params={"cursor":bad})).status_code,422)

    async def test_live_insertions_and_edits_between_requests(self):
        self.collection.rows=[row(i) for i in range(10)]
        first=await self.page({"limit":3})
        self.collection.rows.append(row(20))
        next_page=await self.page({"limit":3,"cursor":first["next_cursor"]})
        self.assertEqual([r["id"] for r in next_page["items"]],[row(i)["id"] for i in (6,5,4)])
        self.collection.rows[9]["date"]="2026-09-01T00:00:00Z"
        self.collection.rows[0]["date"]="2026-11-01T00:00:00Z"
        remainder=await self.page({"limit":100,"cursor":first["next_cursor"]})
        ids={r["id"] for r in remainder["items"]}
        self.assertIn(row(9)["id"],ids);self.assertNotIn(row(0)["id"],ids)

    async def test_direct_id_old_linked_document_sanitized_scoped_and_no_writes(self):
        self.collection.rows=[row(i) for i in range(2001)]
        self.collection.rows[0].update(date="2000-01-01T00:00:00Z",bill_payment_id="p",_shared_intent={"private":1},
                                       request_fingerprint="secret",_reference_revision=8,_id="mongo")
        self.collection.rows.append(row(3000,user_id="other"))
        before=copy.deepcopy(self.collection.rows)
        response=await self.request("/transactions/"+row(0)["id"])
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()["bill_payment_id"],"p")
        self.assertNotIn("_shared",response.text);self.assertNotIn("fingerprint",response.text);self.assertNotIn("_id",response.json())
        for tid in (row(3000)["id"],"missing"):
            self.assertEqual((await self.request("/transactions/"+tid)).status_code,404)
        public=await self.page({"order":"oldest","limit":1})
        self.assertNotIn("_shared",json.dumps(public))
        self.assertEqual(self.collection.rows,before)

    async def test_legacy_endpoint_retains_default_limit_and_array(self):
        self.collection.rows=[row(i) for i in range(2001)]
        response=await self.request("/transactions")
        self.assertEqual(response.status_code,200);self.assertIsInstance(response.json(),list)
        self.assertEqual(len(response.json()),500)
        response=await self.request("/transactions",{"limit":2001})
        self.assertEqual(len(response.json()),2001)

    async def test_invalid_history_and_read_errors_never_fake_empty_success(self):
        for changes in ({"date":"bad"},{"date":None},{"id":None}):
            self.collection.rows=[row(1,**changes)];before=copy.deepcopy(self.collection.rows)
            self.assertEqual((await self.request()).status_code,409)
            self.assertEqual(self.collection.rows,before)
        self.collection.rows=[row(1),row(1)]
        self.assertEqual((await self.request()).status_code,409)
        self.assertEqual((await self.request("/transactions/"+row(1)["id"])).status_code,409)
        self.collection.fail=True
        for path in ("/transactions/page","/transactions/x"):
            response=await self.request(path);self.assertEqual(response.status_code,503)
            self.assertNotIn("synthetic",response.text)


if __name__ == "__main__":unittest.main()
