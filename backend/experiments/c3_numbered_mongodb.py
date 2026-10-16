"""Opt-in C3 prototype, NOT imported by production. New DB retained, never dropped.

python3 -B -m backend.experiments.c3_numbered_mongodb --execute
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
import tracemalloc
import uuid

from pymongo import MongoClient, monitoring
from pymongo.read_concern import ReadConcern
from pymongo.uri_parser import parse_uri
from backend.transaction_history import parse_instant

URI = "mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true"
PREFIX = "test_c3_numbered_prototype_"
DATE_RE = r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,9}))?(Z|[+-]\d{2}:?\d{2})?)?$"


def normalization():
    """No JS and no writes. Strip fraction before BSON conversion; add micros."""
    cap = lambda n, default: {"$ifNull": [{"$arrayElemAt": ["$_x_match.captures", n]}, default]}
    stages = [
        {"$set": {"_x_match": {"$regexFind": {"input": {"$cond": [
            {"$eq": [{"$type": "$date"}, "string"]}, "$date", ""]}, "regex": DATE_RE}}}},
        {"$set": {"_x_fraction": cap(4, ""), "_x_zone": cap(5, "Z")}},
        {"$set": {"_x_zone": {"$cond": [{"$eq": [{"$strLenCP": "$_x_zone"}, 5]},
            {"$concat": [{"$substrCP": ["$_x_zone", 0, 3]}, ":", {"$substrCP": ["$_x_zone", 3, 2]}]}, "$_x_zone"]}}},
        {"$set": {"_x_seconds": {"$convert": {"input": {"$concat": [cap(0, ""), "T", cap(1, "00"), ":",
            cap(2, "00"), ":", cap(3, "00"), "$_x_zone"]}, "to": "date", "onError": None, "onNull": None}},
            "_x_amount": {"$convert": {"input": {"$convert": {"input": {"$cond": [
                {"$or": [{"$eq": ["$amount", ""]}, {"$eq": [{"$ifNull": ["$amount", None]}, None]}]},
                0, "$amount"]}, "to": "string", "onError": None, "onNull": None}},
                "to": "decimal", "onError": None, "onNull": None}}}},
        {"$set": {"_x_time": {"$add": [
            {"$multiply": [{"$convert": {"input": "$_x_seconds", "to": "long", "onNull": None}}, 1000]},
            {"$convert": {"input": {"$substrCP": [{"$concat": ["$_x_fraction", "000000"]}, 0, 6]}, "to": "long"}}]},
            "_x_valid": {"$and": [{"$ne": ["$_x_match", None]}, {"$ne": ["$_x_seconds", None]},
                {"$eq": [{"$type": "$id"}, "string"]}, {"$ne": ["$id", ""]},
                {"$ne": ["$_x_amount", None]}, {"$not": [{"$in": [{"$toString": "$_x_amount"},
                    ["NaN", "Infinity", "-Infinity"]]}]}]}}},
    ]
    return stages


def filtered_pipeline(query, start=None, end=None):
    stages = [{"$match": query}] + normalization()
    bounds = {}
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    def micros(value):
        delta = parse_instant(value) - epoch
        return delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds
    if start is not None: bounds["$gte"] = micros(start)
    if end is not None: bounds["$lt"] = micros(end)
    valid = {"_x_valid": True}
    if bounds: valid["_x_time"] = bounds
    return stages, {"$match": valid}


def sort_fields(order):
    if order not in ("recent", "oldest", "high", "low"): raise ValueError("Unsupported order")
    if order in ("recent", "oldest"):
        direction = -1 if order == "recent" else 1
        return {"_x_time": direction, "id": direction}
    return {"_x_amount": -1 if order == "high" else 1, "_x_time": -1, "id": -1}


def items_pipeline(base, valid, order, page, compact=True):
    if type(page) is not int or page < 1: raise ValueError("Invalid page")
    stages = base + [valid]
    if compact: stages += [{"$project": {"_id": 1, "id": 1, "_x_time": 1, "_x_amount": 1}}]
    stages += [{"$sort": sort_fields(order)}, {"$skip": (page-1)*20}, {"$limit": 20}]
    return stages


def number_page(db, collection, query, order="recent", page=1, start=None, end=None, compact=True):
    if type(page) is not int or page < 1: raise ValueError("Invalid page")
    base, valid = filtered_pipeline(query, start, end)
    with db.client.start_session() as session:
        with session.start_transaction(read_concern=ReadConcern("snapshot")):
            invalid = list(db[collection].aggregate(base + [{"$match": {"_x_valid": False}},
                {"$limit": 1}, {"$project": {"_id": 0, "invalid": {"$literal": True}}}], session=session, maxTimeMS=30000))
            if invalid: raise ValueError("Unverifiable historical candidate")
            counts = list(db[collection].aggregate(base + [valid, {"$count": "total"}], session=session, maxTimeMS=30000))
            total = counts[0]["total"] if counts else 0
            pages = max(1, math.ceil(total/20))
            if page > pages: raise ValueError("Page out of range")
            selected = list(db[collection].aggregate(items_pipeline(base, valid, order, page, compact),
                session=session, allowDiskUse=True, maxTimeMS=30000, batchSize=20))
            # Recover full original docs for only this page, in the same snapshot.
            keys = [r["_id"] for r in selected]
            originals = {r["_id"]: r for r in db[collection].find({"_id": {"$in": keys},
                "user_id": query["user_id"]}, session=session)}
            items = [originals[k] for k in keys]
            return {"items": items, "total": total, "pages": pages, "page": page}


def synthetic(i, padding=2048):
    bases = ["2026-01-01T00:00:00Z", "2024-02-29T23:59:59Z", "2026-03-08T08:00:00Z",
             "2026-11-01T06:30:00Z", "2026-11-01T07:30:00Z", "2026-10-01T12:00:00Z"]
    when = parse_instant(bases[i % len(bases)]) + timedelta(microseconds=(i % 101)*17)
    variant = i % 7
    if variant == 0: text = when.isoformat().replace("+00:00", "Z")
    elif variant in (1,2): text = when.astimezone(timezone(timedelta(minutes=330 if variant==1 else -360))).isoformat()
    elif variant == 3: text = when.replace(tzinfo=None).isoformat()
    elif variant == 4: text = when.date().isoformat()
    elif variant == 5: text = when.isoformat().replace("T", " ").replace(".", ",")
    else: text = when.astimezone(timezone(timedelta(hours=14))).isoformat().replace("+14:00", "+1400")
    identifier = f"synthetic-{i:08d}"
    types = ["income","expense","transfer","debt_payment","loan_given","loan_received"]
    return {"_id": identifier, "id": identifier, "user_id": "other-synthetic" if i%17==0 else "default-user",
            "date": text, "amount": None if i%31==0 else ((i*13)%97-10)/10,
            "type": types[i%6], "account_id": "A" if i%3==0 else "B", "to_account_id": "A" if i%5==0 else "C",
            "category_id": f"C{i%4}", "name": "C3 synthetic", "notes": "x"*padding}


def oracle(size, order, query, start=None, end=None):
    """Reference only: full key sort outside timing/memory measurement of queries."""
    from backend.tests.test_transaction_history import matches
    result = []
    for i in range(size):
        r=synthetic(i,0)
        if not matches(r,query): continue
        when=parse_instant(r["date"],stored=True)
        if start and when<parse_instant(start) or end and when>=parse_instant(end): continue
        result.append((Decimal(str(r["amount"] or 0)),when,r["id"]))
    if order in ("recent","oldest"):
        result.sort(key=lambda r:(r[1],r[2]),reverse=order=="recent")
    else:
        # Stable date/id DESC tie-break for both amount directions.
        result.sort(key=lambda r:(r[1],r[2]),reverse=True)
        result.sort(key=lambda r:r[0],reverse=order=="high")
    return [r[2] for r in result]


class Audit(monitoring.CommandListener):
    def __init__(self,name): self.name=name; self.events=[]; self.violations=[]
    def started(self,event):
        self.events.append((event.database_name,event.command_name))
        admin_allowed={"hello","buildInfo","listDatabases","commitTransaction","abortTransaction","endSessions"}
        if event.database_name not in (self.name,"admin") or event.database_name=="admin" and event.command_name not in admin_allowed:
            self.violations.append((event.database_name,event.command_name))
        if event.command_name in {"drop","dropDatabase","dropIndexes"}: self.violations.append((event.database_name,event.command_name))
    def succeeded(self,event): pass
    def failed(self,event): pass


def explain(db,col,pipeline,allow_disk=True):
    raw=db.command("explain", {"aggregate": col,"pipeline":pipeline,"cursor":{},
        "allowDiskUse":allow_disk,"maxTimeMS":30000},verbosity="executionStats")
    wanted={"stage","nReturned","totalDocsExamined","totalKeysExamined","executionTimeMillis",
            "executionTimeMillisEstimate","usedDisk","spills","spilledBytes","spilledRecords",
            "spilledDataStorageSize","totalDataSizeSortedBytesEstimate","memLimit","limitAmount"}
    results=[]
    def visit(x):
        if isinstance(x,dict):
            info={k:v for k,v in x.items() if k in wanted}
            if "$sort" in x:info["sort_spec"]=x["$sort"]
            if info:results.append(info)
            for v in x.values():visit(v)
        elif isinstance(x,list):
            for v in x:visit(v)
    visit(raw);return results


def execute(sizes,repeats):
    root=Path(__file__).resolve().parents[2]
    assert subprocess.check_output(["git","branch","--show-current"],cwd=root,text=True).strip()=="conflict_280926_1750"
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()=="1ca9972b748dee2ebf613fef1bea7b89e5537b4f"
    assert parse_uri(URI)["nodelist"]==[("127.0.0.1",27018)]
    name=PREFIX+uuid.uuid4().hex; audit=Audit(name)
    client=MongoClient(URI,connect=False,event_listeners=[audit],maxPoolSize=2,
        serverSelectionTimeoutMS=3000,connectTimeoutMS=3000,socketTimeoutMS=45000)
    report={"database":name,"destination":"127.0.0.1:27018","sizes":sizes,"measurements":[],
            "equivalence_checks":0,"retained":True,"production_modified":False}
    output=root/"backend"/"experiments"/"results"/(name+".json")
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        hello=client.admin.command("hello")
        assert client.address==("127.0.0.1",27018) and hello.get("isWritablePrimary")
        assert hello.get("setName")=="app_finanzas_dev_rs" and hello.get("logicalSessionTimeoutMinutes")
        report["server_version"]=client.admin.command("buildInfo")["version"]
        exists=client.admin.command({"listDatabases":1,"filter":{"name":name},"nameOnly":True})["databases"]
        assert not exists,"Exclusive synthetic database already exists; refusing any write"
        assert not audit.violations
        db=client[name]
        print("VERIFIED NEW EXCLUSIVE DB:",name,flush=True)
        db.create_collection("experiment_manifest")
        db.experiment_manifest.insert_one({"_id":"ownership", "purpose":"C3 prototype synthetic ONLY",
            "created_at":datetime.now(timezone.utc),"nonce":name})
        for size in sizes:
            col=f"transactions_{size}";db.create_collection(col)
            for begin in range(0,size,500):
                db[col].insert_many([synthetic(i) for i in range(begin,min(size,begin+500))])
            print("SYNTHETIC INSERTED:",size,flush=True)
            query={"user_id":"default-user"}
            for order in ("recent","oldest","high","low"):
                expected=oracle(size,order,query)
                last=max(1,math.ceil(len(expected)/20))
                for page in sorted({1,2,max(1,last//2),last}):
                    latencies=[];peaks=[]
                    # Warm-up checked separately, not claimed as cold-cache benchmark.
                    actual=number_page(db,col,query,order,page)
                    assert [r["id"] for r in actual["items"]]==expected[(page-1)*20:page*20]
                    assert actual["total"]==len(expected) and actual["pages"]==last
                    assert all(not any(k.startswith("_x_") for k in r) for r in actual["items"])
                    report["equivalence_checks"]+=1
                    for _ in range(repeats):
                        tracemalloc.start();t=time.perf_counter()
                        result=number_page(db,col,query,order,page)
                        latencies.append((time.perf_counter()-t)*1000)
                        peaks.append(tracemalloc.get_traced_memory()[1]);tracemalloc.stop()
                        assert result==actual
                    report["measurements"].append({"size":size,"order":order,"page":page,"total":len(expected),
                        "median_ms":round(statistics.median(latencies),3),"min_ms":round(min(latencies),3),
                        "max_ms":round(max(latencies),3),"client_python_peak_bytes":max(peaks)})
                    print("MEASURE:",size,order,page,round(statistics.median(latencies),1),"ms",flush=True)
                for invalid_page in (0,last+1):
                    try:number_page(db,col,query,order,invalid_page)
                    except ValueError:report["equivalence_checks"]+=1
                    else:raise AssertionError("Invalid/out-of-range page accepted")
            filtered={"user_id":"default-user","category_id":"C0","type":{"$in":["expense","transfer"]},
                      "$or":[{"account_id":"A"},{"type":"transfer","to_account_id":"A"}]}
            start,end="2026-01-01T00:00:00Z","2027-01-01T00:00:00Z"
            expected=oracle(size,"high",filtered,start,end)
            result=number_page(db,col,filtered,"high",1,start,end)
            assert result["total"]==len(expected) and [r["id"] for r in result["items"]]==expected[:20]
            report["equivalence_checks"]+=1
            base,valid=filtered_pipeline(query)
            report.setdefault("explains",[]).append({"size":size,"compact_last":explain(db,col,items_pipeline(base,valid,"recent",last)),
                "wide_last":explain(db,col,items_pipeline(base,valid,"recent",last,False))})
            output.write_text(json.dumps(report,indent=2))
        # Only our synthetic DB: index experiment and changes between requests.
        col=f"transactions_{sizes[-1]}"
        base,valid=filtered_pipeline(filtered,start,end)
        report["filtered_before_index"]=explain(db,col,items_pipeline(base,valid,"high",1))
        db[col].create_index([("user_id",1),("category_id",1),("type",1)],name="synthetic_filter_only")
        report["filtered_after_index"]=explain(db,col,items_pipeline(base,valid,"high",1))
        before=number_page(db,col,query,"recent",1)
        inserted=synthetic(sizes[-1]+1);inserted.update(user_id="default-user",date="2030-01-01T00:00:00Z")
        db[col].insert_one(inserted)
        second=number_page(db,col,query,"recent",2)
        overlap={r["id"] for r in before["items"]}&{r["id"] for r in second["items"]}
        assert overlap
        db[col].update_one({"_id":before["items"][0]["_id"]},{"$set":{"date":"2000-01-01T00:00:00Z"}})
        after=number_page(db,col,query,"recent",1)
        report["live_changes"]={"duplicate_after_insertion":sorted(overlap),"count_before":before["total"],
            "count_after":second["total"],"edition_changes_first_page":after["items"]!=before["items"]}
        report["equivalence_checks"]+=2
        # Malformed legacy candidates: never silently excluded as valid results.
        db.create_collection("invalid_candidates")
        db.invalid_candidates.insert_one(dict(synthetic(1),date="not-a-date",user_id="default-user"))
        try:number_page(db,"invalid_candidates",query)
        except ValueError:report["equivalence_checks"]+=1
        else:raise AssertionError("Ambiguous history silently accepted")
        report["complete"]=True
    except Exception as error:
        report["complete"]=False;report["failure_type"]=type(error).__name__;report["failure"]=str(error)
        raise
    finally:
        report["audit_violations"]=audit.violations
        report["commands_by_database"]={k:sorted({c for d,c in audit.events if d==k}) for k in {d for d,c in audit.events}}
        output.write_text(json.dumps(report,indent=2));client.close()
        print("DB RETAINED (NO CLEANUP):",name,"REPORT:",output,flush=True)
        assert not audit.violations,"Unexpected database command scope"


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--execute",action="store_true")
    parser.add_argument("--sizes",default="501,2001,10001,50001,100001")
    parser.add_argument("--repeats",type=int,default=3);args=parser.parse_args()
    if not args.execute:parser.error("Explicit --execute required; no database connection made")
    sizes=[int(s) for s in args.sizes.split(",")]
    if not sizes or any(n<1 or n>500001 for n in sizes) or not 1<=args.repeats<=5:parser.error("Invalid workload bounds")
    execute(sizes,args.repeats)
