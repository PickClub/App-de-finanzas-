"""Extra isolated equivalence probes; every execution creates a NEW retained DB."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import uuid

from fastapi import HTTPException
from pymongo import MongoClient
from pymongo.uri_parser import parse_uri
from backend.experiments.c3_numbered_mongodb import (
    URI, PREFIX, Audit, filtered_pipeline, items_pipeline, number_page, explain,
)
from backend.transaction_history import parse_instant


def main():
    root=Path(__file__).resolve().parents[2]
    assert subprocess.check_output(["git","branch","--show-current"],cwd=root,text=True).strip()=="conflict_280926_1750"
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()=="1ca9972b748dee2ebf613fef1bea7b89e5537b4f"
    name=PREFIX+uuid.uuid4().hex;assert parse_uri(URI)["nodelist"]==[("127.0.0.1",27018)]
    audit=Audit(name);client=MongoClient(URI,connect=False,event_listeners=[audit],maxPoolSize=2,
        serverSelectionTimeoutMS=3000,connectTimeoutMS=3000,socketTimeoutMS=45000)
    report={"database":name,"retained":True,"cases":[]}
    path=Path(__file__).parent/"results"/(name+"_edges.json")
    try:
        h=client.admin.command("hello")
        assert client.address==("127.0.0.1",27018) and h.get("setName")=="app_finanzas_dev_rs" and h.get("isWritablePrimary")
        assert not client.admin.command({"listDatabases":1,"filter":{"name":name},"nameOnly":True})["databases"]
        db=client[name];db.create_collection("experiment_manifest")
        db.experiment_manifest.insert_one({"_id":"ownership","created_at":datetime.now(timezone.utc),"purpose":"C3 synthetic edges"})
        cases=[
            ("microseconds",["2026-10-01T12:00:00.000001Z","2026-10-01T12:00:00.000002Z"]),
            ("equivalent_offsets",["2026-10-01T08:00:00.123456-04:00","2026-10-01T12:00:00.123456Z"]),
            ("pre_epoch",["1969-12-31T23:59:59.999999Z","1970-01-01T00:00:00Z"]),
            ("leap_day",["2024-02-29T23:59:59.999999Z","2024-03-01T00:00:00Z"]),
            ("dst_repeated_hour",["2026-11-01T01:30:00-05:00","2026-11-01T01:30:00-06:00"]),
            ("nine_fraction_digits",["2026-10-01T12:00:00.123456789Z","2026-10-01T12:00:00.123457Z"]),
            ("date_only_and_naive",["2026-10-01","2026-10-01T00:00:00"]),
            ("invalid_non_leap_day",["2026-02-29T12:00:00Z"]),
            ("invalid_hour",["2026-10-01T25:00:00Z"]),
            ("invalid_offset",["2026-10-01T12:00:00+99:00"]),
            ("legacy_offset_seconds",["2026-10-01T12:00:00+01:02:03"]),
            ("legacy_basic_iso",["20261001T120000Z"]),
        ]
        for name_case,dates in cases:
            col="edge_"+name_case;db.create_collection(col)
            rows=[{"_id":str(i),"id":str(i),"user_id":"default-user","date":value,"amount":70} for i,value in enumerate(dates)]
            db[col].insert_many(rows)
            expected_invalid=False
            try:expected=sorted(rows,key=lambda r:(parse_instant(r["date"],stored=True),r["id"]),reverse=True)
            except HTTPException:expected_invalid=True;expected=[]
            try:actual=number_page(db,col,{"user_id":"default-user"});rejected=False
            except ValueError:actual={"items":[]};rejected=True
            equivalent=(expected_invalid==rejected and (rejected or [r["id"] for r in actual["items"]]==[r["id"] for r in expected]))
            report["cases"].append({"case":name_case,"equivalent":equivalent,"reference_invalid":expected_invalid,"prototype_rejected":rejected})
            print(name_case,report["cases"][-1],flush=True)
        # Floating-point representation versus decimal comparison at close values.
        col="amount_precision";db.create_collection(col)
        amounts=[0.3,0.30000000000000004,0.3000000000000001,1.0000000000000002,1.0]
        rows=[{"_id":str(i),"id":str(i),"user_id":"default-user","date":"2026-10-01T12:00:00Z","amount":a} for i,a in enumerate(amounts)]
        db[col].insert_many(rows)
        actual=number_page(db,col,{"user_id":"default-user"},"high")
        expected=sorted(rows,key=lambda r:(Decimal(str(r["amount"])),r["id"]),reverse=True)
        report["cases"].append({"case":"close_float_amounts","equivalent":[r["id"] for r in actual["items"]]==[r["id"] for r in expected]})
        col="account_graph";db.create_collection(col)
        def movement(identifier,kind,source,target=None,user="default-user"):
            return {"_id":identifier,"id":identifier,"user_id":user,"date":"2026-10-01T12:00:00Z",
                    "type":kind,"account_id":source,"to_account_id":target,"category_id":"C","amount":70}
        db[col].insert_many([movement("incoming","transfer","B","A"),movement("outgoing","transfer","A","B"),
            movement("self","transfer","A","A"),movement("ordinary","expense","A"),
            movement("false-destination","expense","B","A"),movement("other-user","expense","A",user="other")])
        q={"user_id":"default-user","$or":[{"account_id":"A"},{"type":"transfer","to_account_id":"A"}]}
        page=number_page(db,col,q)
        report["cases"].append({"case":"incoming_outgoing_self_and_user_scope","equivalent":
            {r["id"] for r in page["items"]}=={"incoming","outgoing","self","ordinary"} and page["total"]==4})
        empty=number_page(db,col,{"user_id":"absent"})
        report["cases"].append({"case":"empty_results","equivalent":empty["total"]==0 and empty["items"]==[] and empty["pages"]==1})
        q.update(category_id="C",type={"$in":["transfer"]})
        combined=number_page(db,col,q,"low",1,"2026-10-01T00:00:00Z","2026-10-02T00:00:00Z")
        report["cases"].append({"case":"combined_transfer_filters","equivalent":combined["total"]==3})
        none=number_page(db,col,q,"low",1,"2026-10-01T12:00:00Z","2026-10-01T12:00:00Z")
        report["cases"].append({"case":"exclusive_end_equal_window","equivalent":none["total"]==0})
        report["complete"]=True
    finally:
        report["audit_violations"]=audit.violations
        report["commands_by_database"]={d:sorted({c for dbn,c in audit.events if dbn==d}) for d in {d for d,c in audit.events}}
        path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,indent=2));client.close()
        print("DB RETAINED:",name,"REPORT:",path,flush=True)
        assert not audit.violations


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--execute",action="store_true");a=p.parse_args()
    if not a.execute:p.error("Explicit --execute required")
    main()
