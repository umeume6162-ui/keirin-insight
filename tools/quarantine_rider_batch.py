"""Non-destructive triage of rider evidence. Output belongs in private storage.
Any invalid or conflicting record is excluded; no approval or live write.
"""
import argparse
import datetime
import json
from pathlib import Path
from collections import Counter
from prepare_verified_release import digest, need, person
from rider_evidence_intake import candidate

def triage(ledger):
    need(isinstance(ledger,dict) and ledger.get("schema")=="ki-rider-evidence-ledger-v1","ledger schema mismatch")
    entries=ledger.get("entries")
    need(isinstance(entries,list),"entries must be an array")
    hashes=Counter(digest(e.get("observation")) for e in entries if isinstance(e,dict) and isinstance(e.get("observation"),dict))
    records=[]; issues=[]; eligible=[]
    def hold(index,entry,status,code,reason):
        issues.append({"index":index,"entrySha256":digest(entry),"status":status,"code":code,"reason":reason,"original":entry})
    for index,e in enumerate(entries):
        if not isinstance(e,dict) or not isinstance(e.get("observation"),dict):
            hold(index,e,"ERROR","INVALID_ENTRY","Missing observation or malformed entry")
            continue
        if hashes[digest(e["observation"])]>1:
            hold(index,e,"ERROR","DUPLICATE_OBSERVATION","All copies held for reconciliation")
            continue
        state=e.get("status")
        if state=="pending":
            hold(index,e,"PENDING","AWAITING_REVIEW","Independent review not supplied")
            continue
        if state=="rejected":
            hold(index,e,"REJECTED","REVIEW_REJECTED","Explicitly rejected by source ledger")
            continue
        if state!="approved":
            hold(index,e,"ERROR","UNKNOWN_STATUS","Unrecognized evidence status")
            continue
        try:
            record,review=candidate(e["observation"],e.get("approval"))
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError) as exc:
            hold(index,e,"ERROR","VALIDATION_FAILED",str(exc))
            continue
        eligible.append((index,e,record,review))
    ids=Counter(r["id"] for _,_,r,_ in eligible)
    people=Counter(person(r["name"],r["prefecture"],r["period"]) for _,_,r,_ in eligible)
    for index,e,r,v in eligible:
        if ids[r["id"]]>1 or people[person(r["name"],r["prefecture"],r["period"])]>1:
            hold(index,e,"ERROR","IDENTITY_COLLISION","All conflicting candidates held")
        else:
            records.append((r,v))
    issues.sort(key=lambda e:e["index"])
    counts=Counter(e["status"] for e in issues)
    summary={"entries":len(entries),"candidate":len(records),"pending":counts["PENDING"],"rejected":counts["REJECTED"],"error":counts["ERROR"]}
    need(summary["entries"]==sum(summary[k] for k in ("candidate","pending","rejected","error")),"triage count mismatch")
    return {"schema":"ki-rider-quarantine-v1","processedAt":datetime.datetime.now(datetime.timezone.utc).isoformat(),"inputSha256":digest(ledger),"counts":summary,"issues":issues,"candidates":[r for r,_ in records],"reviews":[v for _,v in records],"publicationStatus":"candidate_only"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=triage(json.loads(a.ledger.read_text(encoding="utf-8")))
    # Exclusive creation: prior incident reports remain unchanged.
    with a.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result["counts"]))
    if result["counts"]["error"]:
        raise SystemExit(2)

if __name__=="__main__":
    main()
