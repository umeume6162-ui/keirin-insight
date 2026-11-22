"""Separate observed score metrics and timestamps; no approval or publication."""
from datetime import datetime, timedelta
import re
from audit_evidence_sheet import source_ok, digest
from rider_temporal_history import half_year

METRICS={"profile_current_term":"今期得点","rolling_four_months":"直近4ヶ月競走得点"}
def score_observation(registration, evidence_id, source, metric, raw_value, source_updated_at, retrieved_at, acquisition_method):
    if not isinstance(registration,str) or not re.fullmatch(r"[0-9]{6}",registration) or not source_ok(source,registration):
        raise ValueError("invalid identity or source")
    if not isinstance(evidence_id,str) or not evidence_id.strip():
        raise ValueError("evidence reference required")
    if metric not in METRICS or acquisition_method not in ("cached_official_profile","direct_official_profile"):
        raise ValueError("unknown metric or acquisition method")
    for s in (source_updated_at,retrieved_at):
        if not isinstance(s,str):raise ValueError("timestamp must be text")
    updated=datetime.fromisoformat(source_updated_at)
    retrieved=datetime.fromisoformat(retrieved_at)
    if updated.utcoffset()!=timedelta(hours=9) or retrieved.utcoffset()!=timedelta(hours=9) or updated>retrieved:
        raise ValueError("invalid source chronology")
    if raw_value in (None,"","-","—"):
        value=None;state="MISSING"
    elif isinstance(raw_value,str) and re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}",raw_value):
        value=raw_value;state="OBSERVED_UNVERIFIED"
    else:
        raise ValueError("invalid score representation")
    result={"registration":registration,"evidenceId":evidence_id,"source":source,"metric":metric,"sourceLabel":METRICS[metric],"rawValue":raw_value,"value":value,"state":state,"sourceUpdatedAt":source_updated_at,"retrievedAt":retrieved_at,"sourceCalendarTerm":half_year(updated.date().isoformat()),"reviewTerm":None,"aggregationStart":None,"aggregationEnd":None,"acquisitionMethod":acquisition_method,"isFinalReviewScore":False,"independentApproval":"PENDING","publicationAllowed":False,"trainingAllowed":False}
    result["sha256"]=digest(result)
    return result
