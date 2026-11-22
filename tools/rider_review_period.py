"""Candidate-only review-period evidence, without a regulatory eligibility decision.

Review periods are calendar half-years, not academy graduation cohorts.
Never substitute displayed profile scores for official final review scores.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
import re
from urllib.parse import urlsplit
from audit_evidence_sheet import digest
from rider_temporal_history import review_key

def review_observation(registration, year, half, metric, rule_version, score, source, evidence_id, published_at, retrieved_at):
    key=review_key(registration,year,half,metric,rule_version)
    if not isinstance(score,str) or not re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}",score):
        raise ValueError("explicit official review score required")
    if not isinstance(evidence_id,str) or not evidence_id.strip():
        raise ValueError("evidence required")
    u=urlsplit(source)
    if u.scheme!="https" or u.netloc not in ("keirin.jp","www.keirin.jp") or not u.path or u.path=="/pc/racerprofile":
        raise ValueError("review-specific official source required")
    p=datetime.fromisoformat(published_at); r=datetime.fromisoformat(retrieved_at)
    end=date(year,6,30) if half==1 else date(year,12,31)
    if p.utcoffset()!=timedelta(hours=9) or r.utcoffset()!=timedelta(hours=9) or p>r or p.date()<=end:
        raise ValueError("invalid final-review chronology")
    record={"schema":"ki-review-score-candidate-v1","registration":registration,"year":year,"half":half,"metric":metric,"ruleVersion":rule_version,"score":score,"source":source,"evidenceId":evidence_id,"publishedAt":published_at,"retrievedAt":retrieved_at,"status":"PENDING","officialFinalScoreConfirmed":False,"publicationAllowed":False,"trainingAllowed":False}
    record["sha256"]=digest(record)
    return record

def three_term_summary(records):
    """Arithmetic diagnostic only; no regulatory eligibility conclusion."""
    if len(records)!=3:
        raise ValueError("exactly three terms required")
    r=sorted(records,key=lambda x:(x["year"],x["half"]))
    if len({(x["registration"],x["metric"],x["ruleVersion"]) for x in r})!=1 or any(x["metric"]!="registration_review" for x in r):
        raise ValueError("inconsistent review scope")
    indexes=[2*x["year"]+x["half"] for x in r]
    if indexes!=list(range(indexes[0],indexes[0]+3)):
        raise ValueError("nonconsecutive review terms")
    for x in r:
        if x.get("officialFinalScoreConfirmed") is not True or x.get("status")!="VERIFIED":
            raise ValueError("independently verified final scores required")
    total=sum((Decimal(x["score"]) for x in r),Decimal(0))
    return {"terms":[[x["year"],x["half"]] for x in r],"scoreSum":str(total),"arithmeticMean":str(total/Decimal(3)),"eligibility":None,"regulatoryDecisionMade":False,"publicationAllowed":False}
