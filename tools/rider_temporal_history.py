"""Candidate-only temporal rider history. Never infer final review points or publish."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from audit_evidence_sheet import source_ok, digest

GRADES={"SS","S1","S2","A1","A2","A3","L1"}
def day(value):
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
        raise ValueError("invalid ISO date")
    return date.fromisoformat(value)
def half_year(value):
    d=day(value)
    return f"{d.year}-H{1 if d.month<=6 else 2}"
def profile_candidate(registration, evidence_id, source, profile_date, grade_events, displayed_score=None):
    if not isinstance(registration,str) or not re.fullmatch(r"[0-9]{6}",registration) or not source_ok(source,registration):
        raise ValueError("invalid identity or source")
    if not isinstance(evidence_id,str) or not evidence_id.strip():
        raise ValueError("missing evidence reference")
    cutoff=day(profile_date)
    events=[]; seen=set()
    for item in grade_events:
        effective=item["effectiveFrom"]; d=day(effective); grade=item["grade"]
        if grade not in GRADES or d>cutoff or effective in seen:
            raise ValueError("invalid or conflicting grade event")
        seen.add(effective)
        events.append({"registration":registration,"effectiveFrom":effective,"grade":grade,"effectiveTerm":half_year(effective),"evidenceId":evidence_id,"source":source,"profileDate":profile_date,"status":"PENDING"})
    score=None
    if displayed_score is not None:
        if not isinstance(displayed_score,str) or not re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}",displayed_score):
            raise ValueError("invalid displayed score")
        score={"registration":registration,"label":"今期得点","value":displayed_score,"profileDate":profile_date,"observedTerm":half_year(profile_date),"reviewTerm":None,"isFinalReviewScore":False,"evidenceId":evidence_id,"source":source,"status":"PENDING"}
    result={"schema":"ki-temporal-profile-candidate-v1","registration":registration,"gradeEvents":sorted(events,key=lambda x:x["effectiveFrom"]),"displayedScore":score,"historyComplete":False,"identityApproved":False,"publicationAllowed":False}
    result["candidateSha256"]=digest(result)
    return result

def review_key(registration, year, half, metric, rule_version):
    if not isinstance(registration,str) or not re.fullmatch(r"[0-9]{6}",registration):
        raise ValueError("invalid registration")
    if type(year) is not int or year<1900 or type(half) is not int or half not in (1,2):
        raise ValueError("invalid review period")
    if metric not in ("promotion_review","registration_review") or not isinstance(rule_version,str) or not rule_version.strip():
        raise ValueError("invalid review metric or rules")
    return (registration,year,half,metric,rule_version)
