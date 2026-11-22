"""Versioned quality re-audit; no production writes or new approvals."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from prepare_verified_release import digest, need, NAMES, validate
from quarantine_rider_batch import triage

RULESET="ki-quality-2026-11-22-v1"
MODULES=("prepare_verified_release.py","release_change_audit.py","rider_evidence_intake.py","rider_evidence_batch.py","quarantine_rider_batch.py","stage_rider_release.py","revalidate_quality.py")

def rules():
    root=Path(__file__).resolve().parent
    hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in MODULES}
    return {"version":RULESET,"implementationSha256":digest(hashes),"modules":hashes}

def reaudit(feeds,reviews,ledger):
    policy=rules()
    report={"schema":"ki-quality-reaudit-v1","ruleset":policy,"checkedAt":datetime.datetime.now(datetime.timezone.utc).isoformat(),"inputHashes":{"feeds":digest(feeds),"reviews":digest(reviews),"ledger":digest(ledger)},"publicationPerformed":False}
    try:
        validate(feeds,reviews)
        report["release"]={"status":"structurally_passed","reason":None}
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError) as exc:
        report["release"]={"status":"blocked","reason":str(exc)}
    try:
        result=triage(ledger)
        report["evidence"]={"status":"checked","counts":result["counts"],"quarantine":result}
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError) as exc:
        report["evidence"]={"status":"blocked","reason":str(exc)}
    report["independentApprovalCreated"]=False
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--feeds",type=Path,required=True)
    p.add_argument("--reviews",type=Path,required=True)
    p.add_argument("--ledger",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    load=lambda path:json.loads(path.read_text(encoding="utf-8"))
    feeds=[load(a.feeds/("verified-"+n+"-feed-v1.json")) for n in NAMES]
    report=reaudit(feeds,load(a.reviews),load(a.ledger))
    with a.output.open("x",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    if report["release"]["status"]=="blocked" or report["evidence"]["status"]=="blocked" or report["evidence"]["counts"]["error"]:
        raise SystemExit(2)
if __name__=="__main__":
    main()
