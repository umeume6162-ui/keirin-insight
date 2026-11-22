"""Read a JSON evidence ledger and stage approved rider candidates.
No production writes; never convert pending evidence to approval.
"""
import argparse
import json
from pathlib import Path
from rider_evidence_intake import candidate
from prepare_verified_release import need, digest, person

def collect(ledger):
    need(isinstance(ledger,dict) and ledger.get("schema")=="ki-rider-evidence-ledger-v1","ledger schema mismatch")
    entries=ledger.get("entries")
    need(isinstance(entries,list),"entries must be an array")
    records=[]; reviews=[]; pending=0; rejected=0
    seen=set(); ids=set(); people=set()
    for entry in entries:
        need(isinstance(entry,dict),"invalid entry")
        obs=entry.get("observation")
        need(isinstance(obs,dict),"missing observation")
        h=digest(obs)
        need(h not in seen,"duplicate observation")
        seen.add(h)
        state=entry.get("status")
        need(state in ("pending","rejected","approved"),"unknown evidence status")
        if state=="pending":
            pending+=1
            continue
        if state=="rejected":
            rejected+=1
            continue
        record,review=candidate(obs,entry.get("approval"))
        rid=record["id"]; p=person(record["name"],record["prefecture"],record["period"])
        need(rid not in ids and p not in people,"duplicate approved identity")
        ids.add(rid); people.add(p)
        records.append(record); reviews.append(review)
    return {"schema":"ki-rider-candidate-batch-v1","publicationStatus":"candidate_only","counts":{"entries":len(entries),"pending":pending,"rejected":rejected,"approvedCandidates":len(records)},"riders":records,"reviews":reviews}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    result=collect(json.loads(args.ledger.read_text(encoding="utf-8")))
    with args.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print("Candidate batch staged; no publication performed.")

if __name__=="__main__":
    main()
