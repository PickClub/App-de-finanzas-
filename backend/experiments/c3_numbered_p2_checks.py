"""New DB for adversarial format checks and synthetic index-maintenance timings."""
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess
import time
import uuid

from bson.decimal128 import Decimal128
from fastapi import HTTPException
from pymongo import MongoClient
from pymongo.uri_parser import parse_uri
from backend.experiments.c3_numbered_p2 import URI, PREFIX, Audit, base, fixture, micros, query_page, sort_fields


def main():
    root=Path(__file__).resolve().parents[2]
    assert subprocess.check_output(["git","branch","--show-current"],cwd=root,text=True).strip()=="conflict_280926_1750"
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()=="1ca9972b748dee2ebf613fef1bea7b89e5537b4f"
    assert parse_uri(URI)["nodelist"]==[("127.0.0.1",27018)]
    name=PREFIX+uuid.uuid4().hex;audit=Audit(name)
    client=MongoClient(URI,connect=False,event_listeners=[audit],maxPoolSize=2,serverSelectionTimeoutMS=3000,connectTimeoutMS=3000,socketTimeoutMS=45000)
    report={"database":name,"retained":True,"cases":[],"maintenance":[]}
    path=Path(__file__).parent/"results"/(name+"_checks.json")
    try:
        h=client.admin.command("hello");assert client.address==("127.0.0.1",27018) and h.get("isWritablePrimary") and h.get("setName")=="app_finanzas_dev_rs"
        assert not client.admin.command({"listDatabases":1,"filter":{"name":name},"nameOnly":True})["databases"]
        db=client[name];db.create_collection("manifest");db.manifest.insert_one({"_id":"ownership","created_at":datetime.now(timezone.utc),"purpose":"synthetic P2 extra"})
        cases=["20261001T120000Z","20261001T120000.123456+010203","2026-10-01T12:00:00.123456+01:02:03",
            "2026-10-01T12:00:00.123456-01:02:03","2026-10-01T12:00:00+00:00:00.5",
            "2026-10-01T12:00:00+00:99","1969-12-31T23:59:59.999999Z","2024-02-29",
            "2026-10-01T12:00:00.123456789Z","2026-10-01T25:00:00Z","2026-02-29T12:00:00Z",
            "2026-1001T120000Z","2026-10-01T12:0000Z","2026-W40-4T12:00:00Z"]
        for i,value in enumerate(cases):
            col="case_"+str(i);db.create_collection(col);db[col].insert_one({"_id":"a","id":"a","user_id":"default-user","date":value,"amount":70})
            try:expected=micros(value);invalid=False
            except HTTPException:expected=None;invalid=True
            observed=list(db[col].aggregate(base({"user_id":"default-user"})))[0]
            equivalent=(not observed["_x_valid"]) if invalid else observed["_x_valid"] and expected==observed["_x_time"]
            report["cases"].append({"input":value,"equivalent":bool(equivalent),"reference_invalid":invalid,"prototype_valid":observed["_x_valid"]})
        col="combined_filters";db.create_collection(col)
        rows=[fixture(i,0) for i in range(2001)]
        # Ensure both transfer extremes independently of the fixture's type cycle.
        rows += [dict(fixture(3000,0),type="transfer",account_id="A",to_account_id="B",user_id="default-user"),
                 dict(fixture(3001,0),type="transfer",account_id="B",to_account_id="A",user_id="default-user")]
        for r in rows:r["_p2_amount"]=Decimal128(r["_p2_amount"])
        db[col].insert_many(rows)
        from backend.tests.test_transaction_history import matches
        q={"user_id":"default-user","category_id":"C0","type":{"$in":["expense","transfer"]},
           "$or":[{"account_id":"A"},{"type":"transfer","to_account_id":"A"}]}
        window=("2026-01-01T00:00:00Z","2027-01-01T00:00:00Z")
        expected=[r for r in rows if matches(r,q) and micros(window[0])<=micros(r["date"])<micros(window[1])]
        expected.sort(key=lambda r:(micros(r["date"]),r["id"]),reverse=True)
        for strategy in ("baseline","optimized","stored_keys"):
            actual=query_page(db,col,q,"recent",1,strategy,window=window)
            report["cases"].append({"input":"combined_filters_"+strategy,"equivalent":actual["total"]==len(expected)
                and [r["id"] for r in actual["items"]]==[r["id"] for r in expected[:20]]})
        q.pop("category_id");q.pop("type")
        graph=query_page(db,col,q,"recent",1,"optimized",window=None)
        expected_graph=[r for r in rows if matches(r,q)]
        report["cases"].append({"input":"both_transfer_extremes","equivalent":graph["total"]==len(expected_graph)})
        for indexed in (False,True):
            col="maintenance_"+str(indexed);db.create_collection(col)
            if indexed:
                for order in ("recent","high","low"):
                    db[col].create_index([("user_id",1)]+[(k.replace("_x_","_p2_"),v) for k,v in sort_fields(order).items()],name="synthetic_"+order)
            samples=[];compute=[]
            for batch in range(4):
                t=time.perf_counter();rows=[fixture(i,512) for i in range(batch*500,(batch+1)*500)]
                for r in rows:r["_p2_amount"]=Decimal128(r["_p2_amount"])
                compute.append((time.perf_counter()-t)*1000)
                t=time.perf_counter();db[col].insert_many(rows);elapsed=(time.perf_counter()-t)*1000
                if batch:samples.append(elapsed)
            stats=db.command("collStats",col)
            report["maintenance"].append({"indexed":indexed,"batch_size":500,"median_insert_ms":statistics.median(samples),
                "insert_samples_ms":samples,"key_generation_ms":compute,"total_index_size":stats.get("totalIndexSize"),
                "index_sizes":stats.get("indexSizes")})
        report["complete"]=True
    finally:
        report["audit_violations"]=audit.violations
        report["commands_by_database"]={d:sorted({c for dbn,c in audit.events if dbn==d}) for d in {d for d,c in audit.events}}
        path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,indent=2));client.close()
        print("RETAINED:",name,"REPORT:",path,flush=True)
        print('FORMAT CHECKS:',sum(x['equivalent'] for x in report['cases']),'/',len(report['cases']),flush=True)
        print('MISMATCHES:',[x for x in report['cases'] if not x['equivalent']],flush=True)
        print('MAINTENANCE:',report['maintenance'],flush=True)
        assert not audit.violations


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--execute",action="store_true");a=p.parse_args()
    if not a.execute:p.error("Explicit --execute required")
    main()
