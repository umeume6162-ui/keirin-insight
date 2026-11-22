"""Audit release changes without modifying production files."""
from prepare_verified_release import digest, need, official, day, key

def records(data):
    a,b,i,l=data
    out={}
    def add(kind,k,x):
        k=(kind,k)
        need(k not in out,"duplicate record key")
        out[k]=x
    for x in a["races"]: add("race","|".join(map(str,key(x["date"],x["track_code"],x["race"]))),x)
    for row in b["rows"]:
        x=dict(zip(b["columns"],row))
        add("result","|".join(map(str,(*key(x["date"],x["trackCode"],x["race"]),int(x["number"])))),x)
    for x in i["riders"]: add("rider",x["id"],x)
    for x in l["races"]: add("line",x["id"],x)
    return out

def audit_changes(previous, proposed, corrections):
    old,new=records(previous),records(proposed)
    journal={}
    for e in corrections:
        k=(e["kind"],e["key"])
        need(k not in journal,"duplicate correction")
        journal[k]=e
    changes=[]
    for k in sorted(old.keys() | new.keys()):
        before,after=old.get(k),new.get(k)
        if before==after: continue
        action="add" if before is None else "withdraw" if after is None else "correct"
        if before is not None:
            e=journal.pop(k,None)
            need(e is not None,"missing correction evidence: "+str(k))
            need(e.get("action")==action and e.get("beforeSha256")==digest(before) and e.get("afterSha256")== (digest(after) if after is not None else None),"correction hash mismatch")
            need(official(e.get("source")) and day(e.get("reviewedDate")) and bool(str(e.get("reason") or "").strip()) and bool(str(e.get("reviewer") or "").strip()),"correction provenance missing")
        else:
            e=None
        changes.append({"kind":k[0],"key":k[1],"action":action,"before":before,"after":after,"evidence":e})
    need(not journal,"unused correction records")
    return changes
