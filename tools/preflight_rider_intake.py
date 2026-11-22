"""Read-only V4 preflight. No evidence acquisition, write, approval or publication."""
import re
from audit_evidence_sheet import HEADERS, POLICY, person, source_ok, audit
from audit_dual_intake import audit_streams

def preflight(original, candidate, auto, manual):
    """original: [name,pref,period,registration]; candidate: 19-column intake row."""
    for stream in (auto, manual):
        if not isinstance(stream,list) or not stream or stream[0]!=HEADERS:
            raise ValueError("intake header mismatch")
    issues=[]
    if not isinstance(original,list) or len(original)!=4 or any(not isinstance(v,str) or not v.strip() for v in original):
        return {"eligible":False,"issues":["INVALID_ORIGINAL"]}
    if not isinstance(candidate,list) or len(candidate)!=19 or any(not isinstance(v,str) for v in candidate):
        return {"eligible":False,"issues":["INVALID_CANDIDATE"]}
    if not re.fullmatch(r"[0-9]{6}",original[3]) or not re.fullmatch(r"[0-9]{6}",candidate[10]):
        issues.append("INVALID_REGISTRATION")
    if original[3]!=candidate[10]: issues.append("REGISTRATION_MISMATCH")
    expected=person(*original[:3])
    for fields,prefix in ((candidate[4:7],"ORIGINAL_"),(candidate[7:10],"")):
        for actual,wanted,label in zip(person(*fields),expected,("NAME","PREFECTURE","PERIOD")):
            if not wanted or actual!=wanted: issues.append(prefix+label+"_MISMATCH")
    if candidate[14]!="PENDING" or candidate[16]!="PENDING":
        issues.append("PENDING_REQUIRED")
    if candidate[15]!=POLICY: issues.append("POLICY_MISMATCH")
    if candidate[3] not in ("cached_official_profile","direct_official_profile"):
        issues.append("UNSUPPORTED_METHOD")
    if not all(candidate[i].strip() for i in (0,2,11,12,13)):
        issues.append("MISSING_EVIDENCE")
    if not source_ok(candidate[11],candidate[10]): issues.append("INVALID_SOURCE")
    # Reuse existing audit, including its cross-channel collision checks.
    # Direct observations are validated as candidates in a temporary copy only.
    probe=candidate.copy()
    if probe[3]=="direct_official_profile": probe[14]="MATCH_CANDIDATE"
    if probe[1] not in ("AUTO","MANUAL"): issues.append("INVALID_STREAM")
    else:
        aa=auto+[probe] if probe[1]=="AUTO" else auto
        mm=manual+[probe] if probe[1]=="MANUAL" else manual
        report=audit_streams(aa,mm)
        index=len(aa) if probe[1]=="AUTO" else len(mm)
        rec=next((r for r in report["records"] if r["stream"]==probe[1] and r["sourceRow"]==index),None)
        if rec is None: issues.append("CANDIDATE_NOT_AUDITED")
        else: issues.extend(rec["issues"])
    issues=list(dict.fromkeys(issues))
    return {"eligible":not issues,"issues":issues,"publicationAllowed":False}
