"""V2 race result comparison. Structural candidates only; not source authentication."""
from datetime import date
from quality_v2 import source, norm
import re

def race_key(v):
    d,venue,r=v
    if date.fromisoformat(d).isoformat()!=d or not re.fullmatch(r"[0-9]{2}",venue) or type(r) is not int or not 1<=r<=12:
        raise ValueError("invalid race key")
    return d,venue,r

def core(obs):
    key=race_key(obs["raceKey"])
    grade=norm(obs["grade"])
    if not grade: raise ValueError("missing grade")
    rows=obs["rows"]
    if not isinstance(rows,list) or not 1<=len(rows)<=9: raise ValueError("invalid field")
    size=obs["fieldSize"]
    if type(size) is not int or size!=len(rows): raise ValueError("incomplete field")
    cars={}
    for row in rows:
        car=row["car"]
        if type(car) is not int or not 1<=car<=9 or car in cars: raise ValueError("invalid car")
        name=norm(row["name"]); finish=norm(row["finish"]); status=norm(row["status"])
        if not name or not finish or not status: raise ValueError("missing required result")
        if finish not in ("失格","欠場","棄権","落車","中止") and not re.fullmatch(r"[1-9]",finish): raise ValueError("invalid finish")
        cars[car]=(name,finish,status)
    return key,grade,size,tuple(sorted(cars.items()))

def classify_race(observations):
    valid={}; rejected=[]
    for i,obs in enumerate(observations):
        try:
            site=source(obs); value=core(obs)
            valid.setdefault(site,set()).add(value)
        except (KeyError,TypeError,ValueError,AttributeError) as exc:
            rejected.append({"index":i,"reason":str(exc)})
    values=set().union(*valid.values()) if valid else set()
    grade="C" if len(values)>1 else "S" if len(valid)==3 else "A" if len(valid)==2 else "B" if valid else "D"
    return {"grade":grade,"sources":sorted(valid),"rejected":rejected,"structuralCandidate":grade in ("A","S"),"publicationAllowed":False,"trainingAllowed":False}
