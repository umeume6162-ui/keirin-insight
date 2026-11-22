"""Recheck corrected quarantine entries, retaining the source report.
No network, no generated approvals, no publication.
"""
import argparse
import json
from pathlib import Path
from prepare_verified_release import need, digest
from quarantine_rider_batch import triage

def recover(report, corrections):
    need(isinstance(report,dict) and report.get("schema")=="ki-rider-quarantine-v1","invalid source report")
    need(isinstance(corrections,list),"corrections must be an array")
    original={}
    for issue in report["issues"]:
        index=issue["index"]
        need(index not in original and digest(issue["original"])==issue["entrySha256"],"source issue invalid")
        original[index]=issue
    seen=set()
    entries=[]
    history=[]
    for c in corrections:
        i=c["index"]
        need(i in original and i not in seen,"unknown or duplicate issue")
        seen.add(i)
        old=original[i]
        need(c.get("previousSha256")==old["entrySha256"],"prior record mismatch")
        need(isinstance(c.get("reason"),str) and c["reason"].strip(),"correction reason required")
        new=c["replacement"]
        need(isinstance(new,dict) and isinstance(new.get("observation"),dict),"invalid replacement")
        need(digest(new)!=old["entrySha256"],"no change")
        # Rejected observations require new explicit independent approval before any promotion.
        entries.append(new)
        history.append({"sourceIndex":i,"previousSha256":old["entrySha256"],"replacementSha256":digest(new),"reason":c["reason"]})
    result=triage({"schema":"ki-rider-evidence-ledger-v1","entries":entries})
    return {"schema":"ki-rider-recovery-v1","sourceReportSha256":digest(report),"history":history,"notRetried":len(original)-len(seen),"result":result,"publicationStatus":"candidate_only"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--corrections",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    load=lambda f:json.loads(f.read_text(encoding="utf-8"))
    result=recover(load(a.report),load(a.corrections))
    with a.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result["result"]["counts"]))
    if result["result"]["counts"]["error"]:
        raise SystemExit(2)
if __name__=="__main__":
    main()
