"""V3 comparisons. Explicit fallback domains; structural candidates only."""
from quality_v2 import identity, source as base_source
from quality_v2_race import core
from urllib.parse import urlsplit

BASE={"KEIRIN.JP","CHARILOTO","KDREAMS"}
EXTRA={"keirin.netkeiba.com":"NETKEIRIN","oddspark.com":"ODDSPARK","www.oddspark.com":"ODDSPARK","sp.oddspark.com":"ODDSPARK","winticket.jp":"WINTICKET","www.winticket.jp":"WINTICKET"}
from datetime import datetime,timedelta

def source(obs, fallback):
    u=urlsplit(obs["url"])
    if u.netloc not in EXTRA:
        return base_source(obs)
    if not fallback or u.scheme!="https": raise ValueError("fallback not enabled")
    if datetime.fromisoformat(obs["observedAt"]).utcoffset()!=timedelta(hours=9): raise ValueError("JST required")
    if obs.get("method") not in ("direct","search_cache","retained_original"): raise ValueError("invalid method")
    if not isinstance(obs.get("evidence"),str) or not obs["evidence"].strip(): raise ValueError("missing evidence")
    return EXTRA[u.netloc]

def classify(observations, kind, fallback=False):
    if kind not in ("identity","race"): raise ValueError("unknown kind")
    groups={}; rejected=[]
    for i,obs in enumerate(observations):
        try:
            site=source(obs,fallback)
            key=identity(obs["identity"]) if kind=="identity" else core(obs)
            groups.setdefault(site,set()).add(key)
        except (KeyError,TypeError,ValueError,AttributeError) as exc:
            rejected.append({"index":i,"reason":str(exc)})
    values=set().union(*groups.values()) if groups else set()
    enough=bool(BASE.intersection(groups)) and len(groups)>=2
    grade="C" if len(values)>1 else ("S" if len(groups)>=3 else "A") if enough else "B" if groups else "D"
    return {"grade":grade,"sources":sorted(groups),"rejected":rejected,"structuralCandidate":grade in ("A","S"),"publicationAllowed":False,"trainingAllowed":False}
