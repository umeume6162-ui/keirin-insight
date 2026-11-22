"""Read-only audit of the 19-column evidence sheet. Never approves or publishes."""
import datetime
import hashlib
import json
import re
from collections import Counter, defaultdict
from urllib.parse import urlsplit, parse_qs

HEADERS=["記録ID","記録区分","取得日時（JST）","取得方法","元台帳の氏名","元台帳の府県","元台帳の期別","公式氏名","公式府県","公式期別","公式登録番号（文字列）","公式URL","取得証拠・原文","取得証拠参照","照合判定","検査基準","独立承認状態","元記録ID","備考"]
POLICY="ki-quality-2026-11-22-v1"
def digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def norm(x):
    return "".join(x.split())
def person(name,pref,period):
    p=norm(pref)
    p={"東京都":"東京","大阪府":"大阪","京都府":"京都","北海道":"北海","神奈川県":"神奈","神奈川":"神奈","和歌山県":"和歌","和歌山":"和歌"}.get(p,p)
    if p.endswith("県"):p=p[:-1]
    return (norm(name),p,norm(period).removesuffix("期"))
def source_ok(url,number):
    try:
        u=urlsplit(url)
        return (u.scheme=="https" and u.netloc in ("keirin.jp","www.keirin.jp") and u.path=="/pc/racerprofile" and parse_qs(u.query)=={"snum":[number]} and not u.fragment)
    except ValueError:
        return False
def audit(rows):
    if not isinstance(rows,list) or not rows or rows[0]!=HEADERS:
        raise ValueError("evidence header mismatch")
    checked=[]; ids=defaultdict(list); people=defaultdict(list); numbers=defaultdict(list)
    for i,raw in enumerate(rows[1:],2):
        if isinstance(raw,list) and not any(x is not None and x!="" for x in raw): continue
        item={"row":i,"rawSha256":digest(raw),"issues":[]}
        checked.append(item)
        issues=item["issues"]
        if not isinstance(raw,list) or len(raw)>19 or any(x is not None and not isinstance(x,str) for x in raw):
            issues.append("INVALID_ROW_TYPE");continue
        r=[x or "" for x in raw]+[""]*(19-len(raw))
        item["recordId"]=r[0]
        if r[0]:ids[r[0]].append(item)
        if not r[0] or r[1] not in ("AUTO","MANUAL"):issues.append("INVALID_RECORD")
        if r[14] not in ("MATCH_CANDIDATE","REJECTED","ERROR","PENDING"):issues.append("INVALID_STATUS")
        if r[15]!=POLICY:issues.append("POLICY_RECHECK_REQUIRED")
        if r[16]!="PENDING":issues.append("UNSUPPORTED_APPROVAL")
        # All retained evidence, including pending/cached/rejected rows, contributes
        # to collision detection. Missing fields never create an artificial key.
        if all(r[k].strip() for k in (4,5,6)):
            p=person(*r[4:7]);people[p].append(item)
        if re.fullmatch(r"[0-9]{6}",r[10]):numbers[r[10]].append(item)
        if r[14]!="MATCH_CANDIDATE":
            item["state"]="HELD";continue
        if not all(r[k].strip() for k in (2,3,4,5,6,7,8,9,10,11,12)):issues.append("MISSING_EVIDENCE")
        try:
            d=datetime.datetime.fromisoformat(r[2])
            if d.utcoffset()!=datetime.timedelta(hours=9):raise ValueError()
        except ValueError:issues.append("INVALID_JST")
        if r[3]!="direct_official_profile":issues.append("UNSUPPORTED_METHOD")
        if not re.fullmatch(r"[0-9]{6}",r[10]) or not source_ok(r[11],r[10]):issues.append("INVALID_PROFILE")
        p=person(*r[7:10])
        if p!=person(*r[4:7]):issues.append("IDENTITY_MISMATCH")
        # Index a different observed person too, preventing conflicting identities.
        if all(r[k].strip() for k in (7,8,9)) and (not all(r[k].strip() for k in (4,5,6)) or p!=person(*r[4:7])):
            people[p].append(item)
    for groups,reason in ((ids,"DUPLICATE_RECORD_ID"),(people,"REPEATED_PERSON"),(numbers,"REPEATED_REGISTRATION")):
        for group in groups.values():
            if len(group)>1:
                for item in group:item["issues"].append(reason)
    for item in checked:
        item["state"]="QUARANTINED" if item["issues"] else item.get("state","PENDING_INDEPENDENT_REVIEW")
    return {"schema":"ki-evidence-sheet-audit-v1","policy":POLICY,"inputSha256":digest(rows),"counts":dict(Counter(x["state"] for x in checked)),"records":checked,"publicationAllowed":False}
if __name__=="__main__":
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument("input",type=Path);p.add_argument("output",type=Path);a=p.parse_args()
    data=json.loads(a.input.read_text(encoding="utf-8"))
    report=audit(data)
    with a.output.open("x",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2)
