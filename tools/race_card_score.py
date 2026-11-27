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


def test_prediction_time_check():
    """Regression cases for temporal eligibility."""
    p = "2026-11-28T12:00:00+09:00"
    s = "2026-11-28T12:30:00+09:00"
    cases = [
        (p, p, s, "TIME_PASS"),
        ("2026-11-28T11:59:59+09:00", p, s, "TIME_PASS"),
        ("2026-11-28T12:00:01+09:00", p, s, "HOLD_AFTER_PREDICTION"),
        (s, p, s, "HOLD_POST_START"),
        (p, s, s, "HOLD_POST_START"),
        ("2026-11-28T12:30:01+09:00", p, s, "HOLD_POST_START"),
        (None, p, s, "HOLD_UNKNOWN_TIME"),
        ("2026-11-28T11:00:00", p, s, "HOLD_UNKNOWN_TIME"),
        ("invalid", p, s, "HOLD_UNKNOWN_TIME"),
        (p, p, None, "HOLD_UNKNOWN_TIME"),
    ]
    for observed, predicted, start, expected in cases:
        actual = prediction_time_check(observed, predicted, start)
        if actual != expected:
            raise AssertionError((observed, predicted, start, expected, actual))
    return len(cases)


def prediction_identity_check(expected, observed):
    """Compare canonical race, entrant number and verified identity keys."""
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        return "HOLD_UNKNOWN_IDENTITY"
    for key in ("race_id", "entrant_number", "entrant_id"):
        left, right = expected.get(key), observed.get(key)
        if key == "entrant_number":
            valid = all(type(v) is int and 1 <= v <= 9 for v in (left, right))
        else:
            valid = all(isinstance(v, str) and v.strip() and v == v.strip() for v in (left, right))
        if key == "entrant_id" and valid:
            valid = all(re.fullmatch(r"[0-9]{6}", v) is not None for v in (left, right))
        if not valid:
            return "HOLD_UNKNOWN_IDENTITY"
        if left != right:
            return "HOLD_IDENTITY_MISMATCH"
    return "IDENTITY_MATCH"


def test_prediction_identity_check():
    base = {"race_id": "race-a", "entrant_number": 1, "entrant_id": "000001"}
    cases = [(base, "IDENTITY_MATCH"),
             (dict(base, race_id="race-b"), "HOLD_IDENTITY_MISMATCH"),
             (dict(base, entrant_number=2), "HOLD_IDENTITY_MISMATCH"),
             (dict(base, entrant_id="000002"), "HOLD_IDENTITY_MISMATCH"),
             (dict(base, entrant_id=None), "HOLD_UNKNOWN_IDENTITY"),
             (dict(base, entrant_number=True), "HOLD_UNKNOWN_IDENTITY"),
             (dict(base, entrant_number=10), "HOLD_UNKNOWN_IDENTITY"),
             (dict(base, entrant_number=0), "HOLD_UNKNOWN_IDENTITY"),
             (dict(base, entrant_id="12345"), "HOLD_UNKNOWN_IDENTITY"),
             (dict(base, entrant_id="ABCDEF"), "HOLD_UNKNOWN_IDENTITY")]
    for observed, expected in cases:
        actual = prediction_identity_check(base, observed)
        if actual != expected:
            raise AssertionError((observed, expected, actual))
    return len(cases)



def prediction_input_check(expected, observed, observed_at, predicted_at, start_at, phase, *, acquired_at=None):
    """Candidate eligibility only; provenance and official approval remain separate."""
    if phase != "pre_race":
        return "HOLD_NON_PRE_RACE"
    identity = prediction_identity_check(expected, observed)
    if identity != "IDENTITY_MATCH":
        return identity
    timing = prediction_acquisition_check(observed_at, acquired_at, predicted_at, start_at)
    if timing != "TIME_PASS":
        return timing
    return "CANDIDATE_ONLY"


def test_prediction_input_check():
    base = {"race_id": "race-a", "entrant_number": 1, "entrant_id": "000001"}
    p = "2026-11-28T12:00:00+09:00"
    s = "2026-11-28T12:30:00+09:00"
    cases = [
        (base, p, "pre_race", "CANDIDATE_ONLY"),
        (base, p, "result", "HOLD_NON_PRE_RACE"),
        (base, p, None, "HOLD_NON_PRE_RACE"),
        (dict(base, race_id="race-b"), p, "pre_race", "HOLD_IDENTITY_MISMATCH"),
        (base, s, "pre_race", "HOLD_POST_START"),
        (base, None, "pre_race", "HOLD_UNKNOWN_TIME"),
        (base, "2026-11-28T12:01:00+09:00", "pre_race", "HOLD_AFTER_PREDICTION"),
    ]
    for observed, stamp, phase, expected in cases:
        actual = prediction_input_check(base, observed, stamp, p, s, phase, acquired_at=stamp)
        if actual != expected:
            raise AssertionError((expected, actual))
    extra = [(None, "HOLD_UNKNOWN_TIME"), ("2026-11-28T12:00:01+09:00", "HOLD_AFTER_PREDICTION")]
    for acquired, expected in extra:
        actual = prediction_input_check(base, base, p, p, s, "pre_race", acquired_at=acquired)
        if actual != expected:
            raise AssertionError((expected, actual))
    return len(cases) + len(extra)



def prediction_acquisition_check(observed_at, acquired_at, predicted_at, start_at):
    """Require both observation and actual acquisition before prediction."""
    observation = prediction_time_check(observed_at, predicted_at, start_at)
    if observation != "TIME_PASS":
        return observation
    acquisition = prediction_time_check(acquired_at, predicted_at, start_at)
    if acquisition != "TIME_PASS":
        return acquisition
    from datetime import datetime
    if datetime.fromisoformat(acquired_at) < datetime.fromisoformat(observed_at):
        return "HOLD_ACQUISITION_ORDER"
    return "TIME_PASS"


def test_prediction_acquisition_check():
    o = "2026-11-28T11:00:00+09:00"
    p = "2026-11-28T12:00:00+09:00"
    s = "2026-11-28T12:30:00+09:00"
    cases = [(o, "TIME_PASS"), (p, "TIME_PASS"),
             (None, "HOLD_UNKNOWN_TIME"),
             ("2026-11-28T10:59:59+09:00", "HOLD_ACQUISITION_ORDER"),
             ("2026-11-28T12:00:01+09:00", "HOLD_AFTER_PREDICTION"),
             (s, "HOLD_POST_START")]
    for acquired, expected in cases:
        actual = prediction_acquisition_check(o, acquired, p, s)
        if actual != expected:
            raise AssertionError((acquired, expected, actual))
    return len(cases)


def prediction_feature_coverage(expected, observations, required, predicted_at, start_at):
    """Read-only candidate coverage; never grants training or publication approval."""
    states = {}
    for name in dict.fromkeys(required):
        item = observations.get(name)
        if not isinstance(item, dict) or item.get("value") is None or item.get("value") == "":
            states[name] = "HOLD_MISSING"
            continue
        states[name] = prediction_input_check(
            expected, item.get("identity"), item.get("observed_at"),
            predicted_at, start_at, item.get("phase"),
            acquired_at=item.get("acquired_at"))
    eligible = sum(v == "CANDIDATE_ONLY" for v in states.values())
    return {"required": len(states), "eligible": eligible, "states": states,
            "complete": bool(states) and eligible == len(states),
            "trainingAllowed": False, "publicationAllowed": False}


def test_prediction_feature_coverage():
    identity = {"race_id": "fixture", "entrant_number": 1, "entrant_id": "000001"}
    p = "2026-11-28T12:00:00+09:00"
    s = "2026-11-28T12:30:00+09:00"
    item = {"identity": identity, "value": 0, "observed_at": p,
            "acquired_at": p, "phase": "pre_race"}
    result = prediction_feature_coverage(identity, {"a": item, "b": dict(item, phase="result")},
                                         ["a", "b", "c"], p, s)
    assert result["eligible"] == 1 and result["required"] == 3
    assert result["states"] == {"a": "CANDIDATE_ONLY", "b": "HOLD_NON_PRE_RACE", "c": "HOLD_MISSING"}
    assert not result["complete"] and not result["trainingAllowed"] and not result["publicationAllowed"]
    assert prediction_feature_coverage(identity, {"a": item}, ["a"], p, s)["complete"]
    assert not prediction_feature_coverage(identity, {}, [], p, s)["complete"]
    return 3


if __name__ == "__main__":
    print("prediction timestamp cases:", test_prediction_time_check())
    print("prediction identity cases:", test_prediction_identity_check())
    print("prediction input cases:", test_prediction_input_check())
    print("prediction acquisition cases:", test_prediction_acquisition_check())
    print("prediction coverage cases:", test_prediction_feature_coverage())
