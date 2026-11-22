#!/usr/bin/env python3
"""Strict release preparation. No network access, no self-approval, no live writes.
Input: a complete four-feed release and independently reviewed evidence records.
Output: validated staging directory. Deployment requires separate approval.
"""
import argparse, datetime, hashlib, json, pathlib, re, sys
from urllib.parse import urlsplit, parse_qs
NAMES=("results","rider-results","rider-ids","line-snapshots")
POLICY="ki-verified-only-v1"
def need(ok,msg):
    if not ok: raise ValueError(msg)
def day(s):
    try: return datetime.date.fromisoformat(s).isoformat()==s
    except (ValueError,TypeError): return False
def official(s):
    try:
        u=urlsplit(s)
        return u.scheme=="https" and u.netloc in ("keirin.jp","www.keirin.jp") and bool(u.path)
    except (ValueError,TypeError): return False
def norm(s): return re.sub(r"\s+","",str(s or ""))
def person(n,p,t):
    p=norm(p); return (norm(n),{"神奈川":"神奈","北海道":"北海","和歌山":"和歌"}.get(p,p),str(t))
def key(d,t,r): return (d,str(t),int(r))
def digest(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def review(record,kind,k,evidence):
    v=record.get("officialVerification",{})
    need(v.get("status")=="verified" and official(v.get("source")) and day(record.get("verifiedDate")),f"{kind}: verification metadata missing: {k}")
    e=evidence.get((kind,k))
    need(e is not None and e.get("status")=="approved" and e.get("recordSha256")==digest(record),f"{kind}: independent review missing or content changed: {k}")
    need(e.get("source")==v.get("source") and day(e.get("reviewedDate")) and bool(e.get("reviewer")) and bool(e.get("observedFacts")),f"{kind}: review evidence incomplete: {k}")
def validate(data, reviews):
    a,b,i,l=data
    for j,s in zip(data,("ki-public-results-index-v1","ki-rider-results-v1","ki-official-rider-ids-v1","ki-line-snapshots-v1")):
        need(j.get("schema")==s and j.get("publicationPolicy")==POLICY,"schema / policy mismatch")
    ev={}
    for e in reviews:
        k=(e["kind"],e["key"]); need(k not in ev,"duplicate review"); ev[k]=e
    need(a["source_snapshot_date"]==b["snapshotDate"] and a["latest_race_date"]==b["latestEventDate"],"result feed generation mismatch")
    ids=set(); people=set()
    for x in i["riders"]:
        k=x["id"]; p=person(x["name"],x["prefecture"],x["period"])
        need(re.fullmatch(r"\d{6}",k) and all(p) and re.fullmatch(r"\d+",p[2]) and k not in ids and p not in people,"invalid / duplicate identity")
        need(official(x["source"]) and parse_qs(urlsplit(x["source"]).query).get("snum")==[k],"profile URL mismatch")
        need(set(("name","prefecture","period","id"))<=set(x["officialVerification"]["fields"]),"identity review fields missing")
        review(x,"rider",k,ev); ids.add(k); people.add(p)
    races={}
    for x in a["races"]:
        k=key(x["date"],x["track_code"],x["race"])
        need(day(k[0]) and re.fullmatch(r"\d{2}",k[1]) and 1<=k[2]<=12 and x["size"] in (7,9) and k not in races,"invalid / duplicate race")
        review(x,"race","|".join(map(str,k)),ev); races[k]=x
    cols=b["columns"]
    need(len(set(cols))==len(cols) and set(("date","trackCode","race","number","name","prefecture","period","finishRaw","track","riderClass","sourceUrl"))<=set(cols),"required columns missing")
    groups={k:{} for k in races}; participants=set()
    for row in b["rows"]:
        need(len(row)==len(cols),"row width mismatch")
        x=dict(zip(cols,row)); k=key(x["date"],x["trackCode"],x["race"]); n=int(x["number"])
        need(k in races and 1<=n<=9 and n not in groups[k],"orphan / duplicate rider row")
        p=person(x["name"],x["prefecture"],x["period"])
        need(all(p) and re.fullmatch(r"\d+",p[2]) and norm(x["finishRaw"]) and norm(x["riderClass"]) and official(x["sourceUrl"]) and x["track"]==races[k]["track"],"invalid result row")
        e=ev.get(("result","|".join(map(str,(*k,n)))))
        need(e and e.get("status")=="approved" and e.get("recordSha256")==digest(x) and official(e.get("source")) and day(e.get("reviewedDate")) and e.get("reviewer") and e.get("observedFacts"),"result row review missing")
        groups[k][n]=x; participants.add(p)
    for k,x in races.items(): need(len(groups[k])==x["size"],"race field size mismatch")
    lineids=set()
    for x in l["races"]:
        k=x["id"]; need(k not in lineids and len(x["riders"])==7,"invalid line record"); review(x,"line",k,ev)
        candidates=[rk for rk,r in races.items() if rk[0]==x.get("date") and rk[2]==int(x["race"]) and r["track"]==x.get("track") and r["size"]==7]
        need(len(candidates)==1,"line result not uniquely connected")
        rr=groups[candidates[0]]; nums=set()
        for y in x["riders"]:
            n=int(y["number"]); z=rr.get(n)
            need(z and n not in nums and person(y["name"],y["prefecture"],y["period"])==person(z["name"],z["prefecture"],z["period"]),"line identity mismatch")
            nums.add(n)
        lineids.add(k)
    need(a["summary"]["races"]==b["summary"]["races"]==len(races) and a["summary"]["rider_rows"]==b["summary"]["rows"]==len(b["rows"]) and b["summary"]["riders"]==len(participants),"result summaries mismatch")
    need(i["summary"]["rows"]==len(ids) and l["summary"]["races"]==len(lineids) and l["summary"]["rider_rows"]==sum(len(x["riders"]) for x in l["races"]),"identity / line summaries mismatch")
    need(a["latest_race_date"]==max((k[0] for k in races),default=""),"latest date mismatch")
def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",type=pathlib.Path,required=True); p.add_argument("--reviews",type=pathlib.Path,required=True); p.add_argument("--staging",type=pathlib.Path,required=True); args=p.parse_args()
    filenames=["verified-"+n+"-feed-v1.json" for n in NAMES]
    data=[json.loads((args.input/f).read_text(encoding="utf-8")) for f in filenames]
    reviews=json.loads(args.reviews.read_text(encoding="utf-8"))
    validate(data,reviews)
    need(not args.staging.exists(),"staging already exists; never overwrite")
    args.staging.mkdir(parents=True)
    manifest={}
    for f,j in zip(filenames,data):
        raw=(json.dumps(j,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
        (args.staging/f).write_bytes(raw); manifest[f]=hashlib.sha256(raw).hexdigest()
    (args.staging/"release-manifest.json").write_text(json.dumps({"policy":POLICY,"sha256":manifest},indent=2),encoding="utf-8")
    print("検査合格: staging only; publication not performed")
if __name__=="__main__":
    try: main()
    except (ValueError,KeyError,TypeError,OSError) as e: sys.exit("掲載準備停止: "+str(e))
