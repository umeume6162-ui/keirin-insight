"""Race-card-specific scores, never inferred from a rider profile."""
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
import re
from audit_evidence_sheet import digest

def race_card_score(race_id, race_date, registration, number, raw_score,
                    source, observed_at, evidence_id, aggregation_scope):
    if not isinstance(race_id,str) or not race_id.strip():
        raise ValueError("race ID required")
    if not isinstance(registration,str) or not re.fullmatch(r"[0-9]{6}",registration):
        raise ValueError("six-digit registration required")
    if type(number) is not int or not 1<=number<=9:
        raise ValueError("invalid rider number")
    d=date.fromisoformat(race_date)
    if d.isoformat()!=race_date:raise ValueError("invalid race date")
    t=datetime.fromisoformat(observed_at)
    if t.utcoffset()!=timedelta(hours=9) or t.date()>d:
        raise ValueError("invalid pre-race observation date")
    u=urlsplit(source)
    if u.scheme!="https" or u.netloc not in ("keirin.jp","www.keirin.jp") or not u.path or "racerprofile" in u.path.lower():
        raise ValueError("official race-card evidence required")
    if not isinstance(evidence_id,str) or not evidence_id.strip():
        raise ValueError("evidence ID required")
    if aggregation_scope not in ("rolling_four_months","unknown"):
        raise ValueError("unsupported aggregation scope")
    if raw_score in (None,"","-","—"):
        value=None;state="MISSING"
    elif isinstance(raw_score,str) and re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}",raw_score):
        value=raw_score;state="OBSERVED_UNVERIFIED"
    else:raise ValueError("invalid score")
    record={"schema":"ki-race-card-score-candidate-v1","raceId":race_id,"raceDate":race_date,"registration":registration,"number":number,"rawScore":raw_score,"value":value,"state":state,"source":source,"observedAt":observed_at,"evidenceId":evidence_id,"aggregationScope":aggregation_scope,"profileDisplayAllowed":False,"independentApproval":"PENDING","publicationAllowed":False,"trainingAllowed":False,"preStartTimeVerified":False}
    record["sha256"]=digest(record)
    return record


def prediction_time_check(observed_at, predicted_at, start_at):
    """Check temporal eligibility only; never grant publication or training approval."""
    from datetime import datetime, timedelta
    try:
        times = [datetime.fromisoformat(v) for v in (observed_at, predicted_at, start_at)]
        if any(t.utcoffset() != timedelta(hours=9) for t in times):
            return "HOLD_UNKNOWN_TIME"
    except (ValueError, TypeError):
        return "HOLD_UNKNOWN_TIME"
    observed, predicted, start = times
    if predicted >= start or observed >= start:
        return "HOLD_POST_START"
    if observed > predicted:
        return "HOLD_AFTER_PREDICTION"
    return "TIME_PASS"
