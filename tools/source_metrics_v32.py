"""Aggregate actual attempt records only; no publication or network side effects."""
from collections import defaultdict
from statistics import median

def summarize(records):
    groups=defaultdict(list)
    seen=set()
    for r in records:
        key=r.get("attemptId")
        if not isinstance(key,str) or not key or key in seen:
            raise ValueError("missing or duplicate attemptId")
        if not all(isinstance(r.get(k),str) and r[k] for k in ("source","category","url","observedAt","target")):
            raise ValueError("missing provenance")
        if type(r.get("success")) is not bool or type(r.get("complete")) is not bool:
            raise ValueError("invalid acquisition flags")
        if r["complete"] and not r["success"]:
            raise ValueError("inconsistent flags")
        if r.get("comparison") not in ("match","conflict","not_checked"):
            raise ValueError("invalid comparison status")
        if r["comparison"]!="not_checked" and not r["success"]:
            raise ValueError("comparison without acquisition")
        seen.add(key)
        groups[(r["category"],r["source"])].append(r)
    out=[]
    for (category,source),rows in sorted(groups.items()):
        n=len(rows)
        checked=[r for r in rows if r["comparison"]!="not_checked"]
        times=[r["elapsedMs"] for r in rows if type(r.get("elapsedMs")) in (int,float) and 0<=r["elapsedMs"]<float("inf")]
        out.append({"category":category,"source":source,"attempts":n,"successes":sum(r["success"] for r in rows),"complete":sum(r["complete"] for r in rows),"compared":len(checked),"matches":sum(r["comparison"]=="match" for r in checked),"medianMs":median(times) if times else None,"timed":len(times)})
    return out
