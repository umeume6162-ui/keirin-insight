"""Read-only audit of current publication against independent review records.
Never creates approvals or modifies feeds.
"""
import argparse
import json
from pathlib import Path
from prepare_verified_release import NAMES, validate, digest
from release_change_audit import records

def audit(folder, review_path):
    feeds=[json.loads((folder/("verified-"+n+"-feed-v1.json")).read_text(encoding="utf-8")) for n in NAMES]
    reviews=json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else []
    if not isinstance(reviews,list):
        raise ValueError("Review ledger must be a list")
    idx={}
    for e in reviews:
        k=(e["kind"],e["key"])
        if k in idx: raise ValueError("Duplicate review: "+str(k))
        idx[k]=e
    missing=[]
    for (kind,k),record in records(feeds).items():
        e=idx.get((kind,k))
        if not e or e.get("status")!="approved" or e.get("recordSha256")!=digest(record):
            missing.append({"kind":kind,"key":k,"reason":"missing, unapproved or outdated independent review"})
    error=None
    try: validate(feeds,reviews)
    except (ValueError,KeyError,TypeError,AttributeError) as e: error=str(e)
    return {"status":"blocked" if error or missing else "passed",
            "reviewLedgerPresent":review_path.is_file(),
            "recordCount":len(records(feeds)),
            "missingReviewCount":len(missing),
            "missingReviews":missing,"validationError":error}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--reviews",type=Path,required=True)
    args=p.parse_args()
    try:
        result=audit(args.input,args.reviews)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result["status"]=="passed" else 1
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as e:
        print(json.dumps({"status":"blocked","validationError":str(e)},ensure_ascii=False))
        return 1

if __name__=="__main__":
    raise SystemExit(main())
