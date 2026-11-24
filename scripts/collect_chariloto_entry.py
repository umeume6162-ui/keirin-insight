#!/usr/bin/env python3
"""Conservative one-race Chariloto entry collector. Preview only; never writes Sheets.

Fail closed if the public table cannot be read or lacks a complete 7/9-car field.
Check source terms/robots before expanding to multiple races.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

def compact(value):
    return re.sub(r"[\s　]+", "", unicodedata.normalize("NFKC", str(value or "")))

def parse_entries(html, date, track_code, track, race, source):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    wanted = {"車番","選手名","府県","期別","級班"}
    failures = []
    for table in soup.select("table"):
        trs = table.find_all("tr")
        for head_index, row in enumerate(trs):
            names = [compact(x.get_text(" ", strip=True)) for x in row.find_all(["th","td"], recursive=False)]
            normalized = {label: next((i for i, x in enumerate(names) if label in x), None) for label in wanted}
            if any(v is None for v in normalized.values()) or len(set(normalized.values())) != len(wanted):
                continue
            records = []
            failures = []
            for child in trs[head_index+1:]:
                cells = child.find_all(["td","th"], recursive=False)
                if len(cells) <= max(normalized.values()):
                    continue
                car_raw = compact(cells[normalized["車番"]].get_text(" ", strip=True))
                if not car_raw.isdigit() or not 1 <= int(car_raw) <= 9:
                    continue
                name_cell = cells[normalized["選手名"]]
                anchors = [compact(a.get_text(" ", strip=True)) for a in name_cell.select("a")]
                name = next((a for a in anchors if re.fullmatch(r"[^0-9]+", a) and 2 <= len(a) <= 24), "")
                if not name:
                    name = compact(name_cell.get_text(" ", strip=True))
                pref = compact(cells[normalized["府県"]].get_text(" ", strip=True))
                period = compact(cells[normalized["期別"]].get_text(" ", strip=True)).removesuffix("期")
                grade = compact(cells[normalized["級班"]].get_text(" ", strip=True))
                # Only an explicit foreign designation, not a missing period or 999,
                # permits the invited-rider exception. Preserve the source label.
                invited = pref == "外国"
                if invited and period in ("", "-", "—"):
                    period = ""
                if not name or not pref or not re.fullmatch(r"(?:A[123]|S[12]|L1)", grade) or (not re.fullmatch(r"\d{1,3}", period) and not (invited and period == "")):
                    failures.append("incomplete rider identity")
                    continue
                records.append({"date":date,"trackCode":str(track_code).zfill(2),"track":track,
                    "race":race,"className":grade,"number":int(car_raw),"name":name,
                    "prefecture":pref,"period":period,"preRaceLine":None,
                    "sourceUrl":source,"capturedAt":datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
                    "state":"取得済・未照合","sourceId":"chariloto-racecard"})
            numbers = [r["number"] for r in records]
            if len(records) in (7,9) and sorted(numbers) == list(range(1,len(records)+1)) and not failures:
                return sorted(records,key=lambda x:x["number"])
    diagnostics = []
    for table in soup.select("table")[:8]:
        th = [compact(x.get_text(" ", strip=True))[:28] for x in table.find_all("th")[:12]]
        diagnostics.append({"rows": len(table.find_all("tr")), "headings": th})
    meta = {"htmlChars":len(html), "textChars":len(soup.get_text(" ",strip=True)),
            "tables":len(soup.select("table")), "riderNameVisible":("山崎" in soup.get_text()),
            "riderHeaderVisible":("選手名" in soup.get_text()),
            "scriptTagCount":len(soup.select("script"))}
    raise ValueError("Source HTML did not expose an unambiguous full 7/9-car table; no save. "
                     + (";".join(failures[:2]) if failures else "missing expected table headers")
                     + " sourceShape=" + json.dumps(meta,ensure_ascii=False)
                     + " layouts=" + json.dumps(diagnostics, ensure_ascii=False)[:1900])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date")
    p.add_argument("--track-code")
    p.add_argument("--track")
    p.add_argument("--race",type=int)
    p.add_argument("--out",default="/tmp/keirin-daily-intake-preview.json")
    p.add_argument("--html-fixture",help="Local source HTML; omits live request")
    p.add_argument("--self-test",action="store_true",help="Parse a fictional 7-car HTML table without network or Sheets")
    args=p.parse_args()
    if args.self_test:
        rows="".join(f"<tr><td>{n}</td><td><a>テスト選手{chr(64+n)}</a></td><td>東京</td><td>１００期</td><td>Ａ３</td></tr>" for n in range(1,8))
        html="<table><tr><th>車番</th><th>選手名</th><th>府県</th><th>期別</th><th>級班</th></tr>"+rows+"</table>"
        actual=parse_entries(html,"2026-11-23","26","西武園",1,
            "https://www.chariloto.com/keirin/athletes/2026-11-23/26/1")
        if [v["number"] for v in actual]!=list(range(1,8)):
            raise ValueError("self test did not preserve seven cars")
        try:
            parse_entries(html.replace("<tr><td>7</td>", "<tr><td>6</td>"),"2026-11-23","26","西武園",1,"https://example.org/race")
        except ValueError:
            pass
        else:
            raise ValueError("duplicate/invalid seven-car table was not rejected")
        guest = parse_entries(html.replace("<td>東京</td><td>１００期</td>", "<td>外国</td><td>—</td>", 1),
            "2026-11-23","26","西武園",1,"https://www.chariloto.com/keirin/athletes/2026-11-23/26/1")
        assert guest[0]["prefecture"] == "外国" and guest[0]["period"] == ""
        for bad in (html.replace("<td>１００期</td>", "<td>—</td>", 1),
                    html.replace("<tr><td>7</td>", "<tr><td>8</td>")):
            try:
                parse_entries(bad,"2026-11-23","26","西武園",1,"https://example.org/race")
            except ValueError:
                pass
            else:
                raise AssertionError("Missing domestic period or incomplete car coverage accepted")
        print("SELF_TEST_OK: full field, foreign marker and domestic identity guards")
        return
    if not all([args.date,args.track_code,args.track,args.race]):
        p.error("--date --track-code --track --race are required for live preview")
    datetime.strptime(args.date,"%Y-%m-%d")
    if not args.track_code.isdigit() or not 1<=int(args.track_code)<=99 or not 1<=args.race<=12:
        raise ValueError("invalid track or race")
    url=f"https://www.chariloto.com/keirin/athletes/{args.date}/{int(args.track_code):02d}/{args.race}"
    if args.html_fixture:
        html=Path(args.html_fixture).read_text(encoding="utf-8")
    else:
        import requests
        from urllib.robotparser import RobotFileParser
        agent="KEIRIN-INSIGHT-Research/1.0 (one race read-only test)"
        robots=requests.get("https://www.chariloto.com/robots.txt",timeout=15,
                            headers={"User-Agent":agent})
        if robots.status_code == 200:
            parser=RobotFileParser()
            parser.parse(robots.text.splitlines())
            if not parser.can_fetch(agent,url):
                raise ValueError("Source robots policy disallows requested path")
        elif robots.status_code not in (404,410):
            raise ValueError("Could not establish source robots permissions")
        r=requests.get(url,headers={"User-Agent":agent},timeout=20)
        r.raise_for_status()
        if len(r.content)>3_000_000:
            raise ValueError("source too large")
        html=r.text
    entries=parse_entries(html,args.date,args.track_code,args.track,args.race,url)
    payload={"entries":entries,"results":[],"sourceNote":"One-race preview: unverified, not formal PASS"}
    Path(args.out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PREVIEW_ONLY","race":url,"entries":len(entries),"out":args.out},ensure_ascii=False))

if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("NO_SAVE: "+str(e),file=sys.stderr)
        sys.exit(1)
