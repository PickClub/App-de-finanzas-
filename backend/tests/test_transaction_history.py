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
import asyncio
from unittest.mock import patch
from decimal import Decimal
from bson import BSON, Binary, Int64, ObjectId
from bson.decimal128 import Decimal128

from fastapi import APIRouter, FastAPI, Query
import httpx
from pymongo.errors import OperationFailure
from backend.transaction_history import read_page, read_detail, ReadBudget, exact_amount, parse_instant
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
    def max_time_ms(self, value): self.milliseconds=value;return self
    def batch_size(self, value): self.batch=value;return self
    async def close(self): self.closed=True
    def __aiter__(self): self.iterator = iter(self.rows); return self
    async def __anext__(self):
        try: return next(self.iterator)
        except StopIteration: raise StopAsyncIteration


class Collection:
    def __init__(self): self.rows = []; self.fail = False; self.queries = []; self.aggregations=[];self.cursors=[];self.delay=0
    def find(self, query, projection):
        self.queries.append(copy.deepcopy(query))
        if self.fail: raise OperationFailure("synthetic read failure")
        cursor=Cursor([r for r in self.rows if matches(r, query)]);self.cursors.append(cursor);return cursor
    def aggregate(self, pipeline, **options):
        self.aggregations.append((copy.deepcopy(pipeline),options))
        if self.fail:raise OperationFailure('synthetic aggregate failure')
        self.assert_pipeline(pipeline,options)
        counts={}
        for r in self.rows:
            if matches(r,pipeline[0]['$match']):counts[r.get('id')]=counts.get(r.get('id'),0)+1
        rows=[{'duplicate':True}] if any(n>1 for n in counts.values()) else []
        collection=self
        class AggregateCursor(Cursor):
            async def to_list(self,limit):
                if collection.delay:await asyncio.sleep(collection.delay)
                return await super().to_list(limit)
        cursor=AggregateCursor(rows);self.cursors.append(cursor);return cursor
    @staticmethod
    def assert_pipeline(pipeline,options):
        assert pipeline[1]=={'$group':{'_id':'$id','n':{'$sum':1}}}
        assert pipeline[2]=={'$match':{'n':{'$gt':1}}} and pipeline[3]=={'$limit':1}
        assert options['allowDiskUse'] is False and 0<options['maxTimeMS']<=10000
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
        self.assertEqual(set(result), {"items","has_more","next_cursor","total"})
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
        for params in ({"limit":0},{"limit":101},{"limit":"x"},{"order":"unknown"},
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

    async def test_four_orders_full_histories_and_exact_counts(self):
        for count in (501,2001,10001):
            self.collection.rows=[row(i,amount=str(i%17),date=f'2026-10-{1+i%4:02d}T12:00:00Z') for i in range(count)]
            before=copy.deepcopy(self.collection.rows)
            for order in ('recent','oldest','high','low'):
                expected=sorted(before,key=lambda r:(parse_instant(r['date'],stored=True),r['id']),reverse=order!='oldest')
                if order in ('high','low'):
                    expected.sort(key=lambda r:exact_amount(r['amount']),reverse=order=='high')
                ids=[];params={'order':order,'limit':100}
                while True:
                    result=await self.page(params);self.assertEqual(result['total'],count)
                    ids.extend(r['id'] for r in result['items'])
                    if not result['has_more']:break
                    params['cursor']=result['next_cursor']
                self.assertEqual(ids,[r['id'] for r in expected]);self.assertEqual(len(set(ids)),count)
            self.assertEqual(self.collection.rows,before)

    async def test_exact_decimal128_http_and_cursor_ties(self):
        self.collection.rows=[row(1,amount=Decimal128('1.000000000000000000000000000001')),
            row(2,amount=Decimal128('1.000000000000000000000000000002')),
            row(3,amount='1.000000000000000000000000000002'),
            row(4,amount=Decimal128('1.000000000000000000000000000002'),date='2026-10-02T00:00:00Z')]
        original=[BSON.encode(r) for r in self.collection.rows]
        for order,wanted in [('high',[4,3,2,1]),('low',[1,4,3,2])]:
            params={'order':order,'limit':1};ids=[]
            while True:
                result=await self.page(params);self.assertEqual(result['total'],4)
                ids.extend(x['id'] for x in result['items'])
                self.assertIsInstance(result['items'][0]['amount'],str)
                if not result['has_more']:break
                value=json.loads(base64.urlsafe_b64decode(result['next_cursor']+'='*(-len(result['next_cursor'])%4)))
                self.assertEqual(value['v'],2);params['cursor']=result['next_cursor']
            self.assertEqual(ids,[row(i)['id'] for i in wanted])
        self.assertEqual(original,[BSON.encode(r) for r in self.collection.rows])

    async def test_global_duplicate_ids_outside_filters_and_pages(self):
        self.collection.rows=[row(i) for i in range(501)]
        self.collection.rows.append(row(0,date='2000-01-01T00:00:00Z',account_id='other',category_id='other'))
        for params in ({'limit':1},{'order':'low'},{'account_id':'A','start':'2026-10-01T00:00:00Z'}):
            self.assertEqual((await self.request(params=params)).status_code,409)
        self.collection.rows[-1]['user_id']='other-user'
        result=await self.page({'limit':1});self.assertEqual(result['total'],501)

    async def test_filtered_total_independent_of_cursor_all_orders(self):
        self.collection.rows=[row(1,type='transfer',account_id='B',to_account_id='A'),
            row(2),row(3,category_id='X'),row(4,account_id='B'),row(5,date='2026-10-02T00:00:00Z')]
        for order in ('recent','oldest','high','low'):
            p={'order':order,'account_id':'A','category_id':'C','end':'2026-10-02T00:00:00Z','limit':1}
            a=await self.page(p);b=await self.page(dict(p,cursor=a['next_cursor']))
            self.assertEqual(a['total'],2);self.assertEqual(b['total'],2)
            self.assertFalse(b['has_more']);self.assertIsNone(b['next_cursor'])

    async def test_bson_physical_ids_do_not_change_logical_order(self):
        physical=[1,Int64(2147483648),'mongo',Binary(b'physical',0),ObjectId()]
        self.collection.rows=[row(i,_id=physical[i]) for i in range(5)]
        for order in ('recent','oldest','high','low'):
            result=await self.page({'order':order,'limit':10});self.assertEqual(result['total'],5)
            self.assertTrue(all('_id' not in r for r in result['items']))

    async def test_v1_cursor_bytes_unchanged_and_v2_isolated(self):
        from backend.transaction_history import encode_cursor,scope_hash,iso
        self.collection.rows=[row(i) for i in range(4)]
        context=[self.settings.mongo_url,self.settings.db_name,None]
        filters={'user':'default-user','account':None,'category':None,'types':[],'start':None,'end':None,'order':'recent'}
        token=encode_cursor(scope_hash(context,filters),(parse_instant(row(2)['date'],stored=True),row(2)['id']))
        first=await self.page({'limit':2});self.assertEqual(first['next_cursor'],token)
        self.assertEqual((await self.page({'cursor':token}))['total'],4)
        self.assertEqual((await self.request(params={'order':'high','cursor':token})).status_code,422)
        high=await self.page({'order':'high','limit':1})
        self.assertEqual((await self.request(params={'order':'low','cursor':high['next_cursor']})).status_code,422)
        self.assertEqual((await self.request(params={'cursor':high['next_cursor']})).status_code,422)

    async def test_budgets_fail_without_partial_results_and_close_cursors(self):
        from fastapi import HTTPException
        self.collection.rows=[row(i) for i in range(4)]
        for budget in (ReadBudget(documents=2),ReadBudget(bytes=1)):
            with self.assertRaises(HTTPException) as e:
                await read_page(SimpleNamespace(transactions=self.collection),'default-user',{},lambda x:x,context=[],budget=budget)
            self.assertEqual(e.exception.status_code,503)
            self.assertTrue(all(getattr(c,'closed',False) for c in self.collection.cursors))
        self.collection.delay=.02
        with self.assertRaises(HTTPException) as e:
            await read_page(SimpleNamespace(transactions=self.collection),'default-user',{},lambda x:x,context=[],budget=ReadBudget(seconds=.001))
        self.assertEqual(e.exception.status_code,503)

    async def test_nonfinite_amounts_fail_safely_only_amount_orders(self):
        for value in ('NaN','Infinity','not-money',True):
            self.collection.rows=[row(1,amount=value)]
            self.assertEqual((await self.request(params={'order':'high'})).status_code,409)
        self.collection.rows=[row(1,amount='not-money')]
        self.assertEqual((await self.page())['total'],1)

    async def test_amount_cursor_invalid_values_and_empty_page_total(self):
        self.collection.rows=[row(i) for i in range(3)]
        first=await self.page({'order':'high','limit':1})
        value=json.loads(base64.urlsafe_b64decode(first['next_cursor']+'='*(-len(first['next_cursor'])%4)))
        for change in ({'amount':'NaN'},{'amount':1},{'v':True},{'id':None},{'date':'bad'},{'extra':1}):
            bad=base64.urlsafe_b64encode(json.dumps(dict(value,**change)).encode()).decode().rstrip('=')
            self.assertEqual((await self.request(params={'order':'high','cursor':bad})).status_code,422)
        self.collection.rows=[]
        self.assertEqual((await self.page({'order':'high'}))['total'],0)

    async def test_cpu_deadline_is_checked_without_waiting_for_io(self):
        from fastapi import HTTPException
        self.collection.rows=[row(i) for i in range(10)]
        ticks=iter([0,.1,.2,.3,.4,.6,.7,.8,.9,1])
        with patch('backend.transaction_history.time.monotonic',side_effect=lambda:next(ticks)):
            with self.assertRaises(HTTPException) as e:
                await read_page(SimpleNamespace(transactions=self.collection),'default-user',{},lambda x:x,context=[],budget=ReadBudget(seconds=.5))
        self.assertEqual(e.exception.status_code,503)


if __name__ == "__main__":unittest.main()
