"""Purpose-specific primary source rules; no automatic publication."""
from quality_v3 import source, identity, core

PRIMARY={"identity":{"KEIRIN.JP","WINTICKET"},"race":{"KEIRIN.JP","CHARILOTO","KDREAMS"}}

def classify(observations, kind):
    if kind not in PRIMARY:
        raise ValueError("unknown kind")
    groups={}
    rejected=[]
    for i,obs in enumerate(observations):
        try:
            provider=source(obs, True)
            value=identity(obs["identity"]) if kind=="identity" else core(obs)
            groups.setdefault(provider,set()).add(value)
        except (KeyError,TypeError,ValueError,AttributeError) as exc:
            rejected.append({"index":i,"reason":str(exc)})
    values=set().union(*groups.values()) if groups else set()
    enough=bool(PRIMARY[kind].intersection(groups)) and len(groups)>=2
    grade="C" if len(values)>1 else ("S" if len(groups)>=3 else "A") if enough else "B" if groups else "D"
    return {"grade":grade,"sources":sorted(groups),"rejected":rejected,"structuralCandidate":grade in ("A","S"),"publicationAllowed":False,"trainingAllowed":False}
