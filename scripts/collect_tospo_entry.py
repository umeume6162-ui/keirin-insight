#!/usr/bin/env python3
"""One-race, preview-only source adapter for permitted Tokyo Sports public racecards.

Requires a complete 7/9-car HTML table; rejects missing identity fields.
No Google writes. Intended as a first source adapter, not a general date scraper.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

JST=ZoneInfo("Asia/Tokyo")
def norm(s):
    return unicodedata.normalize("NFKC",str(s or "")).strip()
def parse(html,date,track_code,track,race,url,now=None):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,"html.parser")
    head=norm(soup.get_text(" ",strip=True))
    yyyy,mm,dd=date.split("-")
    # Verify event identity on source; no inferred event/date assignments.
    if track not in head or not re.search(rf"{int(yyyy)}年\s*{int(mm)}月\s*{int(dd)}日",head):
        raise ValueError("Race track/date not independently visible on source")
    # Navigation links can show unrelated races. Prove the requested R via title/heading.
    heading=" ".join(norm(x.get_text(" ",strip=True)) for x in soup.select("title,h1"))
    if not re.search(rf"{re.escape(track)}(?:競輪)?[^\n]{{0,45}}?{int(race)}\s*R(?!\d)",heading):
        raise ValueError("Requested race number absent from main document heading")
    now=now or datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    for table in soup.select("table"):
        h=" ".join(norm(x.get_text(" ",strip=True)) for x in table.select("th"))
        if "車番" not in h or "選手名" not in h:
            continue
        rows=[]
        for tr in table.select("tr"):
            td=tr.find_all("td",recursive=False)
            if len(td)<3:
                continue
            car=norm(td[0].get_text(" ",strip=True))
            if not car.isdigit() or not 1<=int(car)<=9:
                continue
            combined=norm(td[1].get_text(" ",strip=True))
            match=re.match(r"^(.*?)\s+(\d{1,2})歳\s*/\s*([^/]+?)\s*/\s*(\d{1,3})期(?:\s|$)",combined)
            grade_text=norm(td[2].get_text(" ",strip=True))
            grade=re.match(r"^(A[123]|S[12]|L1)(?=\s|$)",grade_text)
            if not match or not grade:
                raise ValueError("Missing named rider/prefecture/period/class in source row for car "+car)
            name=match.group(1).strip()
            pref=match.group(3).strip()
            period=match.group(4)
            if len(name)<2 or not pref:
                raise ValueError("Incomplete rider identity")
            rows.append({"date":date,"trackCode":str(track_code).zfill(2),"track":track,
                         "race":race,"className":grade.group(1),"number":int(car),
                         "name":name,"prefecture":pref,"period":period,
                         "preRaceLine":None,"sourceUrl":url,"capturedAt":now,
                         "state":"取得済・未照合","sourceId":"tokyo-sports-public-racecard"})
        nums=[x["number"] for x in rows]
        if len(rows) in (7,9) and sorted(nums)==list(range(1,len(rows)+1)):
            return sorted(rows,key=lambda x:x["number"])
    raise ValueError("No complete seven/nine-car entry table, no save")
def fetch(url):
    import requests
    u=urlsplit(url)
    if u.scheme!="https" or u.netloc!="keirin.tokyo-sports.co.jp" or not (u.path == "/list/race" or u.path.startswith("/list/race/")):
        raise ValueError("Unsupported source URL")
    agent="KEIRIN-INSIGHT-Research/1.0 (single race read-only)"
    robots=requests.get(f"{u.scheme}://{u.netloc}/robots.txt",headers={"User-Agent":agent},timeout=15)
    if robots.status_code==200:
        p=RobotFileParser()
        p.parse(robots.text.splitlines())
        if not p.can_fetch(agent,url):
            raise ValueError("Robots policy disallows URL")
    elif robots.status_code not in (404,410):
        raise ValueError("Robots permission unavailable")
    r=requests.get(url,headers={"User-Agent":agent},timeout=20)
    r.raise_for_status()
    if len(r.content)>3_000_000:
        raise ValueError("Racecard page too large")
    return r.text
def self_test():
    header="<tr><th>車番</th><th>選手名 年齢/府県/期別</th><th>級 脚</th></tr>"
    rows="".join(f"<tr><td>{n}</td><td>テスト選手{chr(64+n)} 40歳 / 京都 / ９３期</td><td>Ａ３ 両</td></tr>" for n in range(1,8))
    html="<html><body><h1>西武園 2026年11月23日 1R</h1><table>"+header+rows+"</table></body></html>"
    kwargs=dict(date="2026-11-23",track_code="26",track="西武園",race=1,
                url="https://keirin.tokyo-sports.co.jp/list/race/test",now="2026-11-23 07:00 JST")
    parsed=parse(html,**kwargs)
    assert len(parsed)==7 and parsed[0]["className"]=="A3" and parsed[0]["period"]=="93"
    try:
        parse(html.replace("<td>7</td>","<td>6</td>"),**kwargs)
    except ValueError:
        pass
    else:
        raise ValueError("Duplicate car accepted")
    print("SELF_TEST_OK: Tospo full-width and duplicate car validation")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--date")
    p.add_argument("--track-code")
    p.add_argument("--track")
    p.add_argument("--race",type=int)
    p.add_argument("--url")
    p.add_argument("--out",default="/tmp/keirin-tospo-one-race-preview.json")
    args=p.parse_args()
    if args.self_test:
        return self_test()
    if not all([args.date,args.track_code,args.track,args.race,args.url]):
        p.error("--date --track-code --track --race --url required for live preview")
    datetime.strptime(args.date,"%Y-%m-%d")
    html=fetch(args.url)
    entries=parse(html,args.date,args.track_code,args.track,args.race,args.url)
    data={"entries":entries,"results":[],"sourceNote":"One-race preview only; not independent PASS"}
    Path(args.out).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PREVIEW_ONLY","entries":len(entries),"source":"tospo","output":args.out},ensure_ascii=False))
if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("NO_SAVE: "+str(e),file=sys.stderr)
        sys.exit(1)
