"""V2 comparison of already extracted observations. Not proof of retrieval or approval."""
import re
import unicodedata
from urllib.parse import urlsplit
from datetime import datetime, timedelta

HOSTS={"keirin.jp":"KEIRIN.JP","www.keirin.jp":"KEIRIN.JP","chariloto.com":"CHARILOTO","www.chariloto.com":"CHARILOTO","keirin.kdreams.jp":"KDREAMS"}
def norm(value):
    if not isinstance(value,str): raise ValueError("text required")
    return "".join(unicodedata.normalize("NFKC",value).split())
def prefecture(value):
    s=norm(value)
    return {"北海道":"北海","神奈川県":"神奈","神奈川":"神奈","和歌山県":"和歌","和歌山":"和歌","東京都":"東京","大阪府":"大阪","京都府":"京都"}.get(s,s.removesuffix("県"))
def identity(fields):
    name,pref,period,number=fields
    name,pref,period=norm(name),prefecture(pref),norm(period).removesuffix("期")
    if not name or not pref or not re.fullmatch(r"[0-9]+",period) or not isinstance(number,str) or not re.fullmatch(r"[0-9]{6}",number):
        raise ValueError("incomplete identity")
    return (name,pref,period,number)
def source(observation):
    u=urlsplit(observation["url"])
    if u.scheme!="https" or u.netloc not in HOSTS:
        raise ValueError("unapproved source")
    t=datetime.fromisoformat(observation["observedAt"])
    if t.utcoffset()!=timedelta(hours=9): raise ValueError("JST required")
    if observation.get("method") not in ("direct","search_cache","retained_original"):
        raise ValueError("unknown method")
    if not isinstance(observation.get("evidence"),str) or not observation["evidence"].strip():
        raise ValueError("missing evidence")
    return HOSTS[u.netloc]
def classify_identity(observations):
    """Only a structural candidate; raw source must be independently attributable."""
    valid={}; rejected=[]
    for index,obs in enumerate(observations):
        try:
            site=source(obs); key=identity(obs["identity"])
            valid.setdefault(site,set()).add(key)
        except (KeyError,TypeError,ValueError,AttributeError) as exc:
            rejected.append({"index":index,"reason":str(exc)})
    values=set().union(*valid.values()) if valid else set()
    grade="C" if len(values)>1 else "S" if len(valid)==3 else "A" if len(valid)==2 else "B" if valid else "D"
    return {"grade":grade,"sources":sorted(valid),"rejected":rejected,"structuralCandidate":grade in ("A","S"),"publicationAllowed":False,"trainingAllowed":False}
