"""P2 isolation/benchmark only. No production import/startup or prior DB reuse."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
import tracemalloc
import uuid

from pymongo import MongoClient
from pymongo.read_concern import ReadConcern
from pymongo.uri_parser import parse_uri
from backend.transaction_history import parse_instant
from backend.experiments.c3_numbered_mongodb import URI, Audit, synthetic, sort_fields, explain

PREFIX="test_c3_numbered_p2_"
# Basic/extended Gregorian dates, time and offset seconds/fractions; no inference.
PATTERN=r"^(\d{4})-?(\d{2})-?(\d{2})(?:[T ](\d{2})(?::?(\d{2}))?(?::?(\d{2}))?(?:[.,](\d+))?(?:Z|([+-])(\d{2})(?::?(\d{2}))?(?::?(\d{2}))?(?:[.,](\d+))?)?)?$"


def micros(value):
    d=parse_instant(value,stored=True)-datetime(1970,1,1,tzinfo=timezone.utc)
    return d.days*86400000000+d.seconds*1000000+d.microseconds


def normalization():
    cap=lambda i,default: {"$ifNull":[{"$arrayElemAt":["$_x_match.captures",i]},default]}
    integer=lambda i: {"$convert":{"input":cap(i,"0"),"to":"int"}}
    fraction=lambda i: {"$convert":{"input":{"$substrCP":[{"$concat":[cap(i,""),"000000"]},0,6]},"to":"long"}}
    return [
        {"$set":{"_x_match":{"$regexFind":{"input":{"$cond":[{"$eq":[{"$type":"$date"},"string"]},"$date",""]},"regex":PATTERN}}}},
        {"$set":{"_x_seconds":{"$convert":{"input":{"$concat":[cap(0,""),"-",cap(1,""),"-",cap(2,""),"T",cap(3,"00"),":",cap(4,"00"),":",cap(5,"00"),"Z"]},"to":"date","onError":None,"onNull":None}},
            "_x_offset":{"$add":[{"$multiply":[integer(8),3600000000]},{"$multiply":[integer(9),60000000]},{"$multiply":[integer(10),1000000]},fraction(11)]},
            "_x_amount":{"$convert":{"input":{"$convert":{"input":{"$cond":[{"$or":[{"$eq":["$amount",""]},{"$eq":[{"$ifNull":["$amount",None]},None]}]},0,"$amount"]},"to":"string","onError":None,"onNull":None}},"to":"decimal","onError":None,"onNull":None}}}},
        {"$set":{"_x_time":{"$subtract":[{"$add":[{"$multiply":[{"$convert":{"input":"$_x_seconds","to":"long","onNull":None}},1000]},fraction(6)]},
                {"$multiply":["$_x_offset",{"$cond":[{"$eq":[cap(7,"+"),"-"]},-1,1]}]}]},
            "_x_valid":{"$and":[{"$ne":["$_x_match",None]},{"$ne":["$_x_seconds",None]},
                {"$lt":[integer(3),24]},{"$lt":[integer(4),60]},{"$lt":[integer(5),60]},
                {"$lt":["$_x_offset",86400000000]},{"$eq":[{"$type":"$id"},"string"]},{"$ne":["$id",""]},
                {"$ne":["$_x_amount",None]},{"$not":[{"$in":[{"$toString":"$_x_amount"},["NaN","Infinity","-Infinity"]]}]}]}}},
    ]


def fixture(i,padding=2048):
    r=synthetic(i,padding)
    if i%19==0:r["date"]="20261001T120000.123456Z"
    elif i%19==1:r["date"]="2026-10-01T12:00:00.123456+01:02:03"
    r["_p2_time"]=micros(r["date"])
    r["_p2_amount"]=Decimal(str(r["amount"] or 0))
    return r


def oracle(size,order,query):
    from backend.tests.test_transaction_history import matches
    keys=[]
    for i in range(size):
        r=fixture(i,0)
        if matches(r,query):keys.append((r["_p2_amount"],r["_p2_time"],r["id"]))
    if order in ("recent","oldest"):keys.sort(key=lambda k:(k[1],k[2]),reverse=order=="recent")
    else:
        keys.sort(key=lambda k:(k[1],k[2]),reverse=True)
        keys.sort(key=lambda k:k[0],reverse=order=="high")
    return [k[2] for k in keys]


def base(query,window=None):
    stages=[{"$match":query},{"$project":{"_id":1,"id":1,"date":1,"amount":1}}]+normalization()
    if window is not None:
        bounds={}
        if window[0] is not None:bounds["$gte"]=micros(window[0])
        if window[1] is not None:bounds["$lt"]=micros(window[1])
        stages += [{"$match":{"$or":[{"_x_valid":False},{"_x_time":bounds}]}}]
    return stages


def ordered_pipeline(query,order,page,window=None):
    return base(query,window)+[{"$match":{"_x_valid":True}},
        {"$project":{"_id":1,"id":1,"_x_time":1,"_x_amount":1}},
        {"$sort":sort_fields(order)},{"$skip":(page-1)*20},{"$limit":20}]


def facet_pipeline(query,order,page,after=None,window=None):
    pre=base(query,window)
    if after is None:pre += [{"$sort":sort_fields(order)}]
    items=[{"$match":{"_x_valid":True}}]
    if after is not None:
        fields=sort_fields(order);keys=list(fields)
        branches=[]
        for i,key in enumerate(keys):
            branch={k:after[k] for k in keys[:i]}
            branch[key]={"$gt" if fields[key]==1 else "$lt":after[key]}
            branches.append(branch)
        items += [{"$match":{"$or":branches}},{"$sort":fields}]
    else:items += [{"$skip":(page-1)*20}]
    items += [{"$limit":20},{"$project":{"_id":1,"id":1,"_x_time":1,"_x_amount":1}}]
    return pre+[{"$facet":{"invalid":[{"$match":{"_x_valid":False}},{"$limit":1},{"$project":{"_id":0,"bad":{"$literal":True}}}],
        "total":[{"$match":{"_x_valid":True}},{"$count":"n"}],"items":items}}]


def query_page(db,col,query,order,page,strategy="optimized",after=None,window=None):
    if type(page) is not int or page<1:raise ValueError("Invalid page")
    sort_fields(order)
    with db.client.start_session() as session:
        with session.start_transaction(read_concern=ReadConcern("snapshot")):
            if strategy=="stored_keys":
                indexed_query=dict(query)
                if window is not None:
                    indexed_query["_p2_time"]={}
                    if window[0] is not None:indexed_query["_p2_time"]["$gte"]=micros(window[0])
                    if window[1] is not None:indexed_query["_p2_time"]["$lt"]=micros(window[1])
                total=db[col].count_documents(indexed_query,session=session)
                fields=[(k.replace("_x_","_p2_"),v) for k,v in sort_fields(order).items()]
                selected=list(db[col].find(indexed_query,{"_id":1,"id":1},session=session).sort(fields).skip((page-1)*20).limit(20))
            elif strategy=="baseline":
                invalid=list(db[col].aggregate(base(query,window)+[{"$match":{"_x_valid":False}},{"$limit":1}],session=session,maxTimeMS=30000))
                if invalid:raise ValueError("Invalid history")
                counts=list(db[col].aggregate(base(query,window)+[{"$match":{"_x_valid":True}},{"$count":"n"}],session=session,maxTimeMS=30000))
                total=counts[0]["n"] if counts else 0
                selected=list(db[col].aggregate(ordered_pipeline(query,order,page,window),session=session,allowDiskUse=True,maxTimeMS=30000))
            elif strategy in ("optimized","hybrid"):
                result=list(db[col].aggregate(facet_pipeline(query,order,page,after if strategy=="hybrid" else None,window),session=session,allowDiskUse=True,maxTimeMS=30000))[0]
                if result["invalid"]:raise ValueError("Invalid history")
                total=result["total"][0]["n"] if result["total"] else 0;selected=result["items"]
            else:raise ValueError("Unknown strategy")
            pages=max(1,math.ceil(total/20))
            if page>pages:raise ValueError("Out of range")
            ids=[x["_id"] for x in selected]
            originals={x["_id"]:x for x in db[col].find({"_id":{"$in":ids},"user_id":query["user_id"]},session=session)}
            return {"total":total,"pages":pages,"items":[originals[i] for i in ids]}


def timed(action,repeats=3,memory=True):
    samples=[];peaks=[];result=None
    action() # warm-up separate from reported samples
    for _ in range(repeats):
        if memory:tracemalloc.start()
        start=time.perf_counter();result=action();samples.append((time.perf_counter()-start)*1000)
        if memory:peaks.append(tracemalloc.get_traced_memory()[1]);tracemalloc.stop()
    return result,{"median_ms":round(statistics.median(samples),3),"samples_ms":[round(x,3) for x in samples],
        "python_peak_bytes":max(peaks) if peaks else None}


def execute(repeats=3):
    root=Path(__file__).resolve().parents[2]
    assert subprocess.check_output(["git","branch","--show-current"],cwd=root,text=True).strip()=="conflict_280926_1750"
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()=="1ca9972b748dee2ebf613fef1bea7b89e5537b4f"
    assert parse_uri(URI)["nodelist"]==[("127.0.0.1",27018)]
    name=PREFIX+uuid.uuid4().hex;audit=Audit(name)
    client=MongoClient(URI,connect=False,event_listeners=[audit],maxPoolSize=2,serverSelectionTimeoutMS=3000,connectTimeoutMS=3000,socketTimeoutMS=45000)
    report={"database":name,"retained":True,"measurements":[],"controls":[],"explains":[],"checks":0,"edge_cases":[]}
    path=Path(__file__).parent/"results"/(name+".json")
    def save():path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,indent=2,default=str))
    try:
        h=client.admin.command("hello")
        assert client.address==("127.0.0.1",27018) and h.get("setName")=="app_finanzas_dev_rs" and h.get("isWritablePrimary")
        assert h.get("logicalSessionTimeoutMinutes")
        assert not client.admin.command({"listDatabases":1,"filter":{"name":name},"nameOnly":True})["databases"]
        report["server_version"]=client.admin.command("buildInfo")["version"]
        db=client[name];db.create_collection("manifest");db.manifest.insert_one({"_id":"ownership","created_at":datetime.now(timezone.utc),"purpose":"C3 P2 synthetic only"})
        print("VERIFIED NEW DB:",name,flush=True)
        from bson.decimal128 import Decimal128
        for size in (501,2001,10001,50001,100001):
            col="rows_"+str(size);db.create_collection(col)
            for begin in range(0,size,500):
                rows=[fixture(i) for i in range(begin,min(size,begin+500))]
                for r in rows:r["_p2_amount"]=Decimal128(r["_p2_amount"])
                db[col].insert_many(rows)
            start=time.perf_counter()
            for order in ("recent","high","low"):
                fields=[("user_id",1)]+[(k.replace("_x_","_p2_"),v) for k,v in sort_fields(order).items()]
                db[col].create_index(fields,name="synthetic_"+order)
            report.setdefault("index_builds",[]).append({"size":size,"three_indexes_ms":round((time.perf_counter()-start)*1000,3)})
            q={"user_id":"default-user"}
            for order in ("recent","oldest","high","low"):
                expected=oracle(size,order,q);last=max(1,math.ceil(len(expected)/20))
                for strategy in ("baseline","optimized","stored_keys"):
                    for page in (1,last):
                        result,metrics=timed(lambda:query_page(db,col,q,order,page,strategy),repeats)
                        assert [r["id"] for r in result["items"]]==expected[(page-1)*20:page*20]
                        assert result["total"]==len(expected)
                        report["checks"]+=1
                        report["measurements"].append(dict(metrics,size=size,order=order,page=page,strategy=strategy,total=len(expected)))
                        print("P2:",size,order,strategy,page,metrics["median_ms"],"ms",flush=True)
                first=query_page(db,col,q,order,1)
                tail=first["items"][-1]
                after={"_x_time":micros(tail["date"]),"_x_amount":Decimal128(Decimal(str(tail["amount"] or 0))),"id":tail["id"]}
                result,metrics=timed(lambda:query_page(db,col,q,order,2,"hybrid",after),repeats)
                assert [r["id"] for r in result["items"]]==expected[20:40]
                report["checks"]+=1;report["measurements"].append(dict(metrics,size=size,order=order,page=2,strategy="hybrid",total=len(expected)))
            # Independent prefix measurements; NOT exact exclusive stage times.
            controls={"filter_and_count":[{"$match":q},{"$count":"n"}],
                "filter_normalize_count":base(q)+[{"$count":"n"}],
                "filter_normalize_sort_count":base(q)+[{"$sort":sort_fields("recent")},{"$count":"n"}],
                "filter_normalize_sort_last_selection":ordered_pipeline(q,"recent",last)}
            for label,pipeline in controls.items():
                _,metrics=timed(lambda:list(db[col].aggregate(pipeline,allowDiskUse=True,maxTimeMS=30000)),repeats,False)
                report["controls"].append(dict(metrics,size=size,control=label))
            recent_tail=query_page(db,col,q,"recent",1)["items"][-1]
            recent_after={"_x_time":micros(recent_tail["date"]),"id":recent_tail["id"]}
            report["explains"].append({"size":size,"optimized_last":explain(db,col,facet_pipeline(q,"recent",last)),
                "hybrid_second":explain(db,col,facet_pipeline(q,"recent",2,recent_after))})
            print("SIZE COMPLETE:",size,flush=True);save()
        # Cases which were incompatible in P1, plus precision and malformed dates.
        cases=["20261001T120000Z","2026-10-01T12:00:00.123456+01:02:03",
            "2026-10-01T12:00:00.123456-01:02:03","2026-10-01T12:00:00.123456+01:02:03.123456",
            "1969-12-31T23:59:59.999999Z","2024-02-29","2026-11-01T01:30:00-05:00",
            "2026-11-01T01:30:00-06:00","2026-10-01T12:00:00.123456789Z",
            "2026-10-01T12:00:00+00:99","2026-02-29T12:00:00Z","bad"]
        from fastapi import HTTPException
        for i,value in enumerate(cases):
            col="case_"+str(i);db.create_collection(col)
            db[col].insert_one({"_id":"a","id":"a","user_id":"default-user","date":value,"amount":70})
            try:required=micros(value);invalid=False
            except HTTPException:required=None;invalid=True
            aggregate=list(db[col].aggregate(base(q)))[0]
            equivalent=(not aggregate["_x_valid"]) if invalid else aggregate["_x_valid"] and aggregate["_x_time"]==required
            report["edge_cases"].append({"input":value,"equivalent":bool(equivalent),"reference_invalid":invalid,
                "reference_micros":required,"aggregation_micros":aggregate.get("_x_time")})
        # Inter-query view-live changes, only in the freshly created synthetic DB.
        col="rows_100001";first=query_page(db,col,q,"recent",1)
        row=fixture(100002);row.update(_id="new",id="new",user_id="default-user",date="2030-01-01T00:00:00Z",_p2_time=micros("2030-01-01T00:00:00Z"),_p2_amount=Decimal128(Decimal("70")))
        db[col].insert_one(row);second=query_page(db,col,q,"recent",2)
        overlap={r["id"] for r in first["items"]}&{r["id"] for r in second["items"]}
        db[col].update_one({"_id":first["items"][0]["_id"]},{"$set":{"date":"2000-01-01T00:00:00Z","_p2_time":micros("2000-01-01T00:00:00Z")}})
        edited=query_page(db,col,q,"recent",1)
        report["live"]={"overlap_after_insertion":sorted(overlap),"count_before":first["total"],"count_after":second["total"],"edit_changes_page":edited!=first}
        report["complete"]=True
    except Exception as error:
        report["complete"]=False;report["failure"]=str(error);report["failure_type"]=type(error).__name__;raise
    finally:
        report["audit_violations"]=audit.violations
        report["commands_by_database"]={d:sorted({c for dbn,c in audit.events if dbn==d}) for d in {d for d,c in audit.events}}
        save();client.close();print("RETAINED:",name,"REPORT:",path,flush=True)
        assert not audit.violations


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--execute",action="store_true");parser.add_argument("--repeats",type=int,default=3);args=parser.parse_args()
    if not args.execute or not 1<=args.repeats<=5:parser.error("Explicit --execute and repeats 1..5 required")
    execute(args.repeats)
