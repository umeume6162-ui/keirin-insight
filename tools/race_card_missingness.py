"""Classify displayed race-card counts without imputing missing data."""
def classify_count(raw, starts, *, scope_known=False, source_verified=False):
    result={"raw":raw,"value":None,"state":"UNCONFIRMED","trainingAllowed":False}
    if not source_verified:return result
    if raw is None or raw in ("","-","—"):
        result["state"]="MISSING";return result
    if type(raw) is not int or raw<0:
        result["state"]="INVALID";return result
    if not scope_known or starts is None:
        result["state"]="UNKNOWN_SCOPE";return result
    if type(starts) is not int or starts<0 or raw>starts:
        result["state"]="INCONSISTENT";return result
    if starts==0:
        result["state"]="NO_ELIGIBLE_STARTS";return result
    result.update(value=raw,state="OBSERVED_COUNT")
    return result

def rate(numerator, starts, *, scope_known=False, source_verified=False):
    r=classify_count(numerator,starts,scope_known=scope_known,source_verified=source_verified)
    return {**r,"value":r["value"]/starts if r["state"]=="OBSERVED_COUNT" else None}

def split_history(races, transition_date, target_grade, as_of):
    """Use only dated, independently verified records before the prediction date."""
    from datetime import date
    transition=date.fromisoformat(transition_date); cutoff=date.fromisoformat(as_of)
    if transition>cutoff:raise ValueError("future grade transition")
    before=[];after=[];excluded=[]
    for r in races:
        d=date.fromisoformat(r["date"])
        if r.get("independentlyVerified") is not True or d>=cutoff:
            excluded.append(r);continue
        if d<transition:before.append(r)
        elif r.get("gradeAtRace")==target_grade:after.append(r)
        else:excluded.append(r)
    return {"beforeTransition":before,"afterTransitionInGrade":after,"excluded":excluded,"historyComplete":False,"trainingAllowed":False}
