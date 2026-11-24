#!/usr/bin/env python3
"""Read-only metadata enrichment from netkeirin's published race entry table.

Full race identity and all 7/9 rider identities must match the existing
Google-backed daily feed before any metrics are attached. All values carry
the original source URL and the published ~4-month statistical window.
Never writes daily Sheets, V99 or formal verified feeds.
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from discover_tospo_races import VENUE_CODES
from auto_daily_results import canonical_rider_name, canonical_prefecture

JST=ZoneInfo("Asia/Tokyo")
SCHEMA="ki-daily-rider-statistics-v1"
PUBLISHED_WINDOW="直近4か月（netkeirin掲載値）"
HEADERS=["枠","車","","本紙","選手名","競走得点","脚質","S","H","B","逃げ",
         "まくり","差し","マーク","1着","2着","3着","着外","勝率","2連対率",
         "3連対率","ギヤ倍数","選手コメント"]
FIELDS={5:"score",6:"style",7:"s",8:"h",9:"b",10:"escape",11:"sprint",
        12:"difference",13:"mark",14:"first",15:"second",16:"third",
        17:"other",18:"winRate",19:"top2Rate",20:"top3Rate"}
COUNT_FIELDS={"s","h","b","escape","sprint","difference","mark","first","second","third","other"}
RATE_FIELDS={"winRate","top2Rate","top3Rate"}

def clean(value):
    return unicodedata.normalize("NFKC",str(value or "")).replace("\u3000"," ").strip()

def compare_name(value):
    return re.sub(r"\s+","",clean(value))

def source_url(race):
    try:
        if race["track"] not in VENUE_CODES or not 1<=race["race"]<=12:
            return None
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",race["date"]):
            return None
        code=VENUE_CODES[race["track"]]
        return "https://keirin.netkeiba.com/race/entry/?race_id="+race["date"].replace("-","")+code+f'{race["race"]:02d}'
    except (KeyError,TypeError):
        return None

def signature(race):
    entries=race.get("entries") or []
    if len(entries) not in (7,9):
        return None
    try:
        if sorted(x["number"] for x in entries)!=list(range(1,len(entries)+1)):
            return None
        if any(not x.get("name") or not x.get("prefecture") or not x.get("period") for x in entries):
            return None
        identity=[[x["number"],compare_name(x["name"]),clean(x["prefecture"]),
                   clean(x["period"]).removesuffix("期")] for x in sorted(entries,key=lambda e:e["number"])]
        return hashlib.sha256(json.dumps([race["date"],race["track"],race["race"],identity],
                ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
    except (KeyError,TypeError):
        return None

# Only exact, source-observed abbreviations are normalized for daily stat attachment.
# This does NOT change V99, formal rider ID verification, or result acceptance.
STAT_PREFECTURE_ALIASES={"和歌":"和歌山"}
STAT_NAME_ALIASES={"桜井太士":"櫻井太士"}

def stats_name(value):
    name=canonical_rider_name(value)
    return STAT_NAME_ALIASES.get(name,name)

def stats_prefecture(value):
    name=canonical_prefecture(value)
    return STAT_PREFECTURE_ALIASES.get(name,name)

ROBOTS_AGENT="KEIRIN-INSIGHT-Research/1.0 (racecard stat read-only)"

@lru_cache(maxsize=1)
def robots_policy():
    """Check this source's robots policy once per batch, not once per race."""
    resp=requests.get("https://keirin.netkeiba.com/robots.txt",
                      headers={"User-Agent":ROBOTS_AGENT},timeout=15)
    if resp.status_code==200:
        parser=RobotFileParser()
        parser.parse(resp.text.splitlines())
        return parser
    if resp.status_code in (404,410):
        return None
    raise ValueError("Source robots permission uncertain")

def fetch(url):
    u=urlsplit(url)
    if u.scheme!="https" or u.netloc!="keirin.netkeiba.com" or u.path!="/race/entry/":
        raise ValueError("Unsupported netkeirin URL")
    parser=robots_policy()
    if parser is not None and not parser.can_fetch(ROBOTS_AGENT,url):
        raise ValueError("Source robots policy does not allow racecard")
    page=requests.get(url,headers={"User-Agent":ROBOTS_AGENT},timeout=20)
    page.raise_for_status()
    if len(page.content)>3_000_000:
        raise ValueError("Racecard too large")
    return page.text

def extract(html,race,url):
    soup=BeautifulSoup(html,"html.parser")
    title=clean(soup.title.get_text(" ",strip=True) if soup.title else "")
    y,m,d=map(int,race["date"].split("-"))
    if (race["track"] not in title or
        not re.search(rf"{y}年\s*0?{m}月\s*0?{d}日",title) or
        not re.search(rf"(?<!\d){race['race']}\s*R(?!\d)",title)):
        raise ValueError("Race title does not prove meeting/date/race")
    tables=[]
    for table in soup.select("table.RaceCard_Table"):
        head=table.select_one("tr.Header")
        if not head:continue
        labels=[clean(c.get_text(" ",strip=True)).replace(" ","").replace("｜","ー")
                for c in head.find_all(["th","td"],recursive=False)]
        check=[clean(x).replace(" ","").replace("｜","ー") for x in HEADERS]
        if (len(labels)==len(check) and labels[4].startswith("選手名")
                and "府県" in labels[4] and "期別" in labels[4]
                and all(labels[i]==check[i] for i in range(len(check)) if i!=4)):
            tables.append(table)
    if len(tables)!=1:
        raise ValueError("Unique full-name racecard table not found")
    table=tables[0]
    recorded=[]
    for row in table.select("tr.PlayerList"):
        cells=row.find_all("td",recursive=False)
        if len(cells)!=len(HEADERS):raise ValueError("Racecard column count changed")
        car=clean(cells[1].get_text(" ",strip=True))
        if not car.isdigit() or not 1<=int(car)<=9:
            raise ValueError("Invalid car number in source")
        info=clean(cells[4].get_text(" ",strip=True))
        # Full display name is between the katakana reading and favorite link,
        # followed by the prefecture, age and rider training cohort.
        match=re.search(r"^[ァ-ヴー・\s]+\s+(.+?)\s+お気に入り選手\s+(\S+)\s+\d+歳\s+(\d+)期\b",info)
        if not match:raise ValueError("Full rider identity not exposed")
        name,prefecture,period=match.groups()
        values={}
        for index,key in FIELDS.items():
            raw=clean(cells[index].get_text(" ",strip=True))
            if key=="score":
                if not re.fullmatch(r"\d{2,3}\.\d{2}",raw):raise ValueError("No score")
                values[key]=raw
            elif key=="style":
                match_style=re.fullmatch(r"(?:[123]\s*)?(逃|両|追)",raw)
                if not match_style:raise ValueError("No valid riding style")
                values[key]=match_style.group(1)
            elif key in COUNT_FIELDS:
                if not re.fullmatch(r"\d{1,3}",raw):raise ValueError("Missing count "+key)
                values[key]=int(raw)
            elif key in RATE_FIELDS:
                if not re.fullmatch(r"(?:100(?:\.0)?|\d{1,2}(?:\.\d+)?)%",raw):
                    raise ValueError("Missing rate "+key)
                values[key]=raw
        recorded.append({"number":int(car),"name":name,"prefecture":prefecture,
                         "period":period,**values})
    entries=race["entries"]
    if len(recorded)!=len(entries) or len(recorded) not in (7,9):
        raise ValueError("Rider row count does not match Google-backed feed")
    expected={x["number"]:x for x in entries}
    if set(x["number"] for x in recorded)!=set(expected):
        raise ValueError("Car number coverage conflict")
    for source in recorded:
        original=expected[source["number"]]
        mismatches=[]
        if stats_name(source["name"])!=stats_name(original["name"]):mismatches.append("name")
        if stats_prefecture(source["prefecture"])!=stats_prefecture(original["prefecture"]):mismatches.append("prefecture")
        if clean(source["period"])!=clean(original["period"]).removesuffix("期"):mismatches.append("period:"+clean(source["period"])+" / "+clean(original["period"]))
        if mismatches:
            raise ValueError("Rider identity mismatch in source car "+str(source["number"])+": "+",".join(mismatches))
    return {str(x["number"]):{k:v for k,v in x.items()
             if k not in ("number","name","prefecture","period")} for x in recorded}

def hold_reason(exc):
    """Stable diagnostic category; never store exception text or page content."""
    message=str(exc)
    if "Race title does not prove" in message:
        return "race_identity_unproven"
    if "Unique full-name racecard table not found" in message or "Racecard column count changed" in message:
        return "source_table_shape"
    if "Full rider identity not exposed" in message:
        return "source_rider_identity_missing"
    if "Rider identity mismatch" in message or "Car number coverage conflict" in message:
        return "rider_identity_conflict"
    if "Rider row count does not match" in message:
        return "incomplete_source_field"
    if "Missing " in message or "No score" in message or "No valid riding style" in message:
        return "source_stat_missing"
    if "robots" in message.lower() or "permission" in message.lower():
        return "source_access_policy"
    if isinstance(exc,requests.exceptions.RequestException):
        return "source_transport"
    return "unclassified_source_error"

def enrich(board,cache,loader=fetch,limit=16):
    if board.get("schema")!="ki-daily-board-v1" or not isinstance(board.get("races"),list):
        raise ValueError("Unknown daily feed schema")
    if cache.get("schema")!=SCHEMA or not isinstance(cache.get("races"),dict):
        raise ValueError("Unknown stats cache schema")
    if not 1<=limit<=30:raise ValueError("Invalid per-run limit")
    old=cache["races"]
    # Failed source rows are retried after a bounded cooldown; entry changes
    # invalidate holds immediately. This cache never represents a "no race".
    old_holds=cache.get("holds",{})
    if not isinstance(old_holds,dict):
        raise ValueError("Invalid source hold cache")
    now=datetime.now(JST)
    next_cache={}
    next_holds={}
    pending=[]
    counts={"cached":0,"fetched":0,"held":0,"notApplicable":0,"cooldown":0}
    for race in board["races"]:
        for entry in race.get("entries",[]):
            entry.pop("riderStats",None)
        race.pop("riderStatsSource",None)
        url=source_url(race)
        sig=signature(race)
        if not url or not sig:
            counts["notApplicable"]+=1
            continue
        record=old.get(race.get("key"))
        if (isinstance(record,dict) and record.get("signature")==sig and
            record.get("sourceUrl")==url and isinstance(record.get("rows"),dict) and
            len(record["rows"])==len(race["entries"]) and
            set(record["rows"])==set(str(x["number"]) for x in race["entries"])):
            attach(race,record)
            next_cache[race["key"]]=record
            counts["cached"]+=1
        else:
            blocked=old_holds.get(race.get("key"))
            if (isinstance(blocked,dict) and blocked.get("sourceUrl")==url and
                blocked.get("signature")==sig and isinstance(blocked.get("nextRetryAt"),str)):
                try:
                    if datetime.fromisoformat(blocked["nextRetryAt"])>now:
                        next_holds[race["key"]]=blocked
                        counts["cooldown"]+=1
                        continue
                except (ValueError,TypeError):
                    pass
            pending.append((race,url,sig))
    # Prefer the current meeting over future cards that may not yet contain
    # rider statistics. Never let tomorrow repeatedly starve todays races.
    today=datetime.now(JST).date()
    pending.sort(key=lambda x:(abs((datetime.strptime(x[0]["date"],"%Y-%m-%d").date()-today).days),
                               x[0]["date"]>today.isoformat(),x[0]["track"],x[0]["race"]))
    for race,url,sig in pending[:limit]:
        try:
            rows=extract(loader(url),race,url)
            record={"sourceUrl":url,"signature":sig,"capturedAt":datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
                    "period":PUBLISHED_WINDOW,"rows":rows}
            attach(race,record)
            next_cache[race["key"]]=record
            counts["fetched"]+=1
        except Exception as exc:
            print("RIDER_STATS_HOLD",race["key"],type(exc).__name__,str(exc)[:120],file=sys.stderr)
            counts["held"]+=1
            # Current-day sources change more quickly than future schedules.
            race_date=datetime.strptime(race["date"],"%Y-%m-%d").date()
            hours=4 if race_date==now.date() else 12
            next_holds[race["key"]]={"sourceUrl":url,"signature":sig,
               "lastAttemptAt":now.isoformat(timespec="seconds"),
               "nextRetryAt":(now+timedelta(hours=hours)).isoformat(timespec="seconds"),
               "reasonType":type(exc).__name__,
               "reasonCode":hold_reason(exc)}
    counts["deferred"]=max(0,len(pending)-limit)
    cache["races"]=dict(sorted(next_cache.items()))
    cache["holds"]=dict(sorted(next_holds.items()))
    return counts

def attach(race,record):
    for entry in race["entries"]:
        entry["riderStats"]=record["rows"][str(entry["number"])]
    race["riderStatsSource"]={"url":record["sourceUrl"],"capturedAt":record["capturedAt"],
                              "period":record["period"],"status":"single_source_unverified"}

def self_test():
    url="https://keirin.netkeiba.com/race/entry/?race_id=202611233403"
    race={"key":"2026-11-23|川崎|3","date":"2026-11-23","track":"川崎","race":3,
          "entries":[{"number":n,"name":f"テスト太郎{n}","prefecture":"宮城","period":"98"} for n in range(1,8)]}
    header="<tr class='Header'>"+"".join("<th>"+("選手名 府県 年齢 期別 級班" if i==4 else h)+"</th>" for i,h in enumerate(HEADERS))+"</tr>"
    items=[]
    for n in range(1,8):
        values=["1",str(n),"","1",f"テストタロウ テスト太郎{n} お気に入り選手 宮城 46歳 98期 A3",
                "73.42","1 逃","6","10","5","5","0","6","0","7","4","5","11","25.9%","40.7%","59.3%","3.92","自力で。"]
        items.append("<tr class='PlayerList'>"+"".join("<td>"+v+"</td>" for v in values)+"</tr>")
    html="<title>川崎競輪 2026年11月23日 3R 出走表</title><table class='RaceCard_Table'>"+header+"".join(items)+"</table>"
    board={"schema":"ki-daily-board-v1","races":[race]}
    cache={"schema":SCHEMA,"races":{}}
    result=enrich(board,cache,lambda _:html,1)
    assert result["fetched"]==1 and race["entries"][0]["riderStats"]["b"]==5
    assert canonical_rider_name("國井裕樹")==canonical_rider_name("国井裕樹")
    assert canonical_prefecture("神奈")==canonical_prefecture("神奈川")
    assert stats_prefecture("和歌")==stats_prefecture("和歌山")
    assert stats_name("桜井太士")==stats_name("櫻井太士")
    assert stats_name("桜井太士")!=stats_name("桜井太郎")
    assert stats_prefecture("和歌")!=stats_prefecture("大阪")
    assert race["entries"][0]["riderStats"]["winRate"]=="25.9%"
    assert enrich(board,cache,lambda _:(_ for _ in ()).throw(AssertionError("no fetch")),1)["cached"]==1
    race["entries"][0]["name"]="別選手"
    hold=enrich(board,cache,lambda _:html,1)
    assert hold["held"]==1 and all("riderStats" not in x for x in race["entries"])
    assert cache["races"]=={} and cache["holds"][race["key"]]["reasonType"]=="ValueError"
    assert cache["holds"][race["key"]]["reasonCode"]=="rider_identity_conflict"
    assert hold_reason(ValueError("Race title does not prove meeting/date/race"))=="race_identity_unproven"
    assert hold_reason(ValueError("Unique full-name racecard table not found"))=="source_table_shape"
    assert hold_reason(ValueError("No score"))=="source_stat_missing"
    assert hold_reason(requests.exceptions.Timeout("test"))=="source_transport"
    blocked=enrich(board,cache,lambda _:(_ for _ in ()).throw(AssertionError("cooldown fail")),1)
    assert blocked["cooldown"]==1 and blocked["fetched"]==0
    assert not any(e.get("riderStats") for e in race["entries"])
    # A further rider change must invalidate a hold rather than keep it forever.
    race["entries"][0]["name"]="新しい別選手"
    called=[0]
    def check_retry(_):
        called[0]+=1
        return html
    recheck=enrich(board,cache,check_retry,1)
    assert recheck["held"]==1 and called==[1]
    # Verify one robots lookup serves multiple racecards but still gates each URL.
    import unittest.mock as mock
    calls=[]
    class FakeResp:
        def __init__(self,status,body):
            self.status_code=status
            self.text=body
            self.content=body.encode()
        def raise_for_status(self):
            if self.status_code!=200:raise ValueError("HTTP")
    def fake_get(url,**kwargs):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return FakeResp(200,"User-agent: *\\nDisallow: /blocked/\\nAllow: /race/entry/\\n")
        return FakeResp(200,"<html>racecard</html>")
    robots_policy.cache_clear()
    with mock.patch.object(requests,"get",side_effect=fake_get):
        first=fetch("https://keirin.netkeiba.com/race/entry/?race_id=202611233403")
        second=fetch("https://keirin.netkeiba.com/race/entry/?race_id=202611233404")
        assert first==second=="<html>racecard</html>"
        assert sum(url.endswith("robots.txt") for url in calls)==1 and len(calls)==3
    robots_policy.cache_clear()
    print("SELF_TEST_OK: full 7-car stats, identity-binding, bounded cooldown, robots batch cache")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--feed",default="daily-board-feed-v1.json")
    p.add_argument("--cache",default="daily-rider-stats-v1.json")
    p.add_argument("--limit",type=int,default=16)
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test:return self_test()
    board_path,cache_path=Path(a.feed),Path(a.cache)
    board=json.loads(board_path.read_text(encoding="utf-8"))
    cache=json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {"schema":SCHEMA,"races":{}}
    stats=enrich(board,cache,limit=a.limit)
    new_board=json.dumps(board,ensure_ascii=False,indent=2)+"\n"
    new_cache=json.dumps(cache,ensure_ascii=False,indent=2)+"\n"
    if board_path.read_text(encoding="utf-8")!=new_board:
        board_path.write_text(new_board,encoding="utf-8")
    if not cache_path.exists() or cache_path.read_text(encoding="utf-8")!=new_cache:
        cache_path.write_text(new_cache,encoding="utf-8")
    print("DAILY_RIDER_STATS",json.dumps(stats,ensure_ascii=False))

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("DAILY_STATS_ABORT",type(exc).__name__,file=sys.stderr)
        sys.exit(1)
