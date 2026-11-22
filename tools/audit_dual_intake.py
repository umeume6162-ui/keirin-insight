"""Audit two independent evidence intake streams; read-only, no publication."""
import json
from pathlib import Path
from audit_evidence_sheet import HEADERS, audit, digest

def audit_streams(auto, manual):
    for rows in (auto,manual):
        if not isinstance(rows,list) or not rows or rows[0]!=HEADERS:
            raise ValueError("intake header mismatch")
    combined=[HEADERS]
    locations=[]
    for mode, rows in (("AUTO",auto),("MANUAL",manual)):
        for line,row in enumerate(rows[1:],2):
            combined.append(row)
            locations.append((mode,line,row))
    report=audit(combined)
    for record in report["records"]:
        mode,line,row=locations[record["row"]-2]
        record["stream"]=mode
        record["sourceRow"]=line
        if not isinstance(row,list) or len(row)<2 or row[1]!=mode:
            record["issues"].append("WRONG_INTAKE_STREAM")
            record["state"]="QUARANTINED"
    from collections import Counter
    report["counts"]=dict(Counter(r["state"] for r in report["records"]))
    report["schema"]="ki-dual-intake-audit-v1"
    report["sourceHashes"]={"auto":digest(auto),"manual":digest(manual)}
    report["publicationAllowed"]=False
    return report

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("auto",type=Path)
    p.add_argument("manual",type=Path)
    p.add_argument("output",type=Path)
    a=p.parse_args()
    load=lambda p:json.loads(p.read_text(encoding="utf-8"))
    result=audit_streams(load(a.auto),load(a.manual))
    with a.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
