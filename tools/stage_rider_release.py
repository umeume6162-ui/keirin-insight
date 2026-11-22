"""Integrate an explicit, access-controlled evidence ledger into a staging release.
This command never changes production feeds or generates approvals.
"""
import argparse
import copy
import json
from pathlib import Path
from prepare_verified_release import NAMES, need, validate, person, digest, day
from rider_evidence_batch import collect

def merge(previous, reviews, ledger, snapshot_date):
    need(day(snapshot_date), "invalid snapshot date")
    validate(previous, reviews)
    batch=collect(ledger)
    proposed=copy.deepcopy(previous)
    existing={r["id"]:r for r in proposed[2]["riders"]}
    people={person(r["name"],r["prefecture"],r["period"]):r["id"] for r in existing.values()}
    combined=copy.deepcopy(reviews)
    added=0
    for r,e in zip(batch["riders"],batch["reviews"]):
        rid=r["id"]
        p=person(r["name"],r["prefecture"],r["period"])
        if rid in existing:
            need(digest(existing[rid])==digest(r),"existing identity differs; use correction workflow")
            continue
        need(p not in people,"identity collision; use correction workflow")
        need(r["verifiedDate"]<=snapshot_date,"future observation")
        existing[rid]=r
        people[p]=rid
        combined.append(e)
        added+=1
    proposed[2]["riders"]=sorted(existing.values(),key=lambda r:r["id"])
    proposed[2]["summary"]["rows"]=len(existing)
    proposed[2]["snapshotDate"]=snapshot_date
    validate(proposed,combined)
    from release_change_audit import audit_changes
    changes=audit_changes(previous,proposed,[])
    return proposed,combined,changes,{"added":added,"pending":batch["counts"]["pending"],"rejected":batch["counts"]["rejected"]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--previous",type=Path,required=True)
    p.add_argument("--reviews",type=Path,required=True)
    p.add_argument("--ledger",type=Path,required=True)
    p.add_argument("--date",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    names=["verified-"+n+"-feed-v1.json" for n in NAMES]
    load=lambda path:json.loads(path.read_text(encoding="utf-8"))
    previous=[load(a.previous/n) for n in names]
    proposed,reviews,changes,counts=merge(previous,load(a.reviews),load(a.ledger),a.date)
    need(not a.output.exists(),"output already exists")
    a.output.mkdir(parents=True)
    def write(name,obj):
        with (a.output/name).open("x",encoding="utf-8") as f:
            json.dump(obj,f,ensure_ascii=False,indent=2)
    for name,obj in zip(names,proposed):
        write(name,obj)
    write("reviews.json",reviews)
    write("corrections.json",[])
    write("candidate-summary.json",{"status":"staged_only","counts":counts,"changeCount":len(changes)})
    print("Staging only; separately run prepare_verified_release and authorize deployment.")

if __name__=="__main__":
    main()
