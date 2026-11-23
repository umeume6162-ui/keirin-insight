#!/usr/bin/env python3
"""Build the DAILY viewing feed from existing Sheets, without changing V99 or verified data."""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SHEET_ID = "1gCe5q5STYH0T8XKqxJbVawB0Cl8TPsCISFJiRUdA02M"
SOURCES = ("AI事前出走スナップ", "V99選手結果蓄積")
JST = ZoneInfo("Asia/Tokyo")

def clean(value):
    return str(value or "").strip()

def fetch_sheets():
    import google.auth.transport.requests
    from google.oauth2 import service_account
    import requests
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON; no output modified")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(creds_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    creds.refresh(google.auth.transport.requests.Request())
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + SHEET_ID + "/values:batchGet"
    params = [("ranges", "'AI事前出走スナップ'!A1:O250"),
              ("ranges", "'V99選手結果蓄積'!A1:W10000"),
              ("ranges", "'KI｜日次出走表'!A1:O10000"),
              ("ranges", "'KI｜日次結果'!A1:O10000")]
    response = requests.get(url, params=params, headers={"Authorization": "Bearer " + creds.token}, timeout=50)
    response.raise_for_status()
    values = response.json().get("valueRanges", [])
    if len(values) != 4:
        raise RuntimeError("Google Sheets did not return both source ranges")
    return [x.get("values", []) for x in values]

def parse_date(s):
    return bool(re.fullmatch(r"20\d\d-\d\d-\d\d", clean(s)))

def bounded_rows(values, minimum_headers):
    if not values or len(values[0]) < minimum_headers:
        raise ValueError("Unexpected source sheet headers; no feed published")
    return values[1:]

def build(entry_values, result_values, today):
    # Today +/- 2 days: current entries and latest completed results, not old archive.
    start, end = today - timedelta(days=2), today + timedelta(days=2)
    grouped = {}
    latest_entries, latest_results = "", ""
    for row in bounded_rows(entry_values, 15):
        r = [clean(x) for x in row] + [""] * max(0, 15 - len(row))
        if not parse_date(r[1]) or not r[2] or not r[3]:
            continue
        latest_entries = max(latest_entries, r[1])
        day = datetime.strptime(r[1], "%Y-%m-%d").date()
        if not start <= day <= end:
            continue
        if not r[5].isdigit() or not 1 <= int(r[5]) <= 9 or not r[6]:
            continue
        key = f"{r[1]}|{r[2]}|{int(r[3])}"
        o = grouped.setdefault(key, {"key": key, "date": r[1], "track": r[2],
                                    "race": int(r[3]), "className": r[4],
                                    "entries": [], "results": [], "status": "entry_only",
                                    "entrySource": "AI事前出走スナップ",
                                    "resultSource": "V99選手結果蓄積"})
        if not any(x["number"] == int(r[5]) for x in o["entries"]):
            o["entries"].append({"number": int(r[5]), "name": r[6], "prefecture": r[7] or None,
                                 "period": r[8] or None, "preRaceLine": r[9] or None,
                                 "position": r[10] or None, "capturedAt": r[13] or None,
                                 "sourceUrl": r[14] or None})
    for row in bounded_rows(result_values, 23):
        r = [clean(x) for x in row] + [""] * max(0, 23 - len(row))
        if not parse_date(r[0]) or not r[1] or not r[4]:
            continue
        latest_results = max(latest_results, r[0])
        day = datetime.strptime(r[0], "%Y-%m-%d").date()
        if not start <= day <= end:
            continue
        if not r[7].isdigit() or not 1 <= int(r[7]) <= 9 or not r[8]:
            continue
        key = f"{r[0]}|{r[1]}|{int(r[4])}"
        o = grouped.setdefault(key, {"key": key, "date": r[0], "track": r[1],
                                    "race": int(r[4]), "className": r[12],
                                    "entries": [], "results": [], "status": "results_partial",
                                    "entrySource": "AI事前出走スナップ",
                                    "resultSource": "V99選手結果蓄積"})
        if not any(x["number"] == int(r[7]) for x in o["results"]):
            o["results"].append({"number": int(r[7]), "name": r[8], "prefecture": r[10] or None,
                                 "period": r[11] or None, "finish": r[6],
                                 "method": r[15] or None, "exception": r[17] or None,
                                 "sourceUrl": r[21] or None})
    races = list(grouped.values())
    for race in races:
        race["entries"].sort(key=lambda x: x["number"])
        race["results"].sort(key=lambda x: int(x["finish"]) if x["finish"].isdigit() else 99)
        nums = [x["number"] for x in race["results"]]
        size = len(race["entries"]) if race["entries"] else len(nums)
        race["status"] = ("results_recorded" if len(nums) in (7, 9) and len(set(nums)) == len(nums)
                          else "results_partial" if nums else "entry_only")
        # Recorded = input data present, NOT two-source PASS or confirmed finish.
        race["expectedCount"] = size
    races.sort(key=lambda x: (x["date"], x["track"], x["race"]))
    return {"schema": "ki-daily-board-v1", "targetDate": today.isoformat(),
            "windowStart": start.isoformat(), "windowEnd": end.isoformat(),
            "sourceLatest": {"entries": latest_entries or None, "results": latest_results or None},
            "verification": "source_sheet_unverified_do_not_treat_as_formal_PASS",
            "races": races,
            "summary": {"races": len(races), "entries": sum(len(x["entries"]) for x in races),
                        "resultRows": sum(len(x["results"]) for x in races)}}

def merge_new(board, entry_values, result_values, today):
    """Prefer fresh intake tabs for the same race, while retaining legacy archive only as fallback.

    Fresh results do not invent missing pre-race entries and do not get marked PASS.
    """
    if not entry_values or not result_values:
        raise ValueError("Daily intake tabs absent")
    if entry_values[0] != ["開催日","場コード","競輪場","R","級班","車番","選手名","府県","期別",
                            "発走前ライン","元URL","取得日時JST","収集状態","レースキー","ソースID"]:
        raise ValueError("Daily entry sheet header changed")
    if result_values[0] != ["開催日","場コード","競輪場","R","級班","車番","選手名","府県","期別",
                             "着順原文","決まり手","個人状況・例外","元URL","取得日時JST","レースキー"]:
        raise ValueError("Daily result sheet header changed")
    by_key = {race["key"]: race for race in board["races"]}
    start = today - timedelta(days=2)
    end = today + timedelta(days=2)
    kinds = (("entries", entry_values[1:]), ("results", result_values[1:]))
    for kind, rows in kinds:
        latest = board["sourceLatest"][kind] or ""
        for row in rows:
            r = [clean(x) for x in row] + [""] * max(0, 15 - len(row))
            if not parse_date(r[0]) or not r[1] or not r[2] or not r[3].isdigit():
                continue
            latest = max(latest, r[0])
            day = datetime.strptime(r[0], "%Y-%m-%d").date()
            if not start <= day <= end or not r[5].isdigit() or not 1 <= int(r[5]) <= 9:
                continue
            key = f"{r[0]}|{r[2]}|{int(r[3])}"
            item = by_key.setdefault(key, {"key":key, "date":r[0], "track":r[2],
                "race":int(r[3]), "className":r[4], "entries":[], "results":[],
                "status":"entry_only", "entrySource":"KI｜日次出走表",
                "resultSource":"KI｜日次結果"})
            if kind == "entries":
                item["entrySource"] = "KI｜日次出走表"
                values = {"number":int(r[5]),"name":r[6],"prefecture":r[7] or None,
                          "period":r[8] or None,"preRaceLine":r[9] or None,
                          "position":None,"capturedAt":r[11] or None,
                          "sourceUrl":r[10] or None}
            else:
                item["resultSource"] = "KI｜日次結果"
                values = {"number":int(r[5]),"name":r[6],"prefecture":r[7] or None,
                          "period":r[8] or None,"finish":r[9],
                          "method":r[10] or None,"exception":r[11] or None,
                          "sourceUrl":r[12] or None}
            # A race may have historical rows from legacy source: replace individual car.
            old = item[kind]
            item[kind] = [x for x in old if x["number"] != int(r[5])]
            item[kind].append(values)
        board["sourceLatest"][kind] = latest or None
    for race in by_key.values():
        race["entries"].sort(key=lambda x:x["number"])
        race["results"].sort(key=lambda x:int(x["finish"]) if str(x["finish"]).isdigit() else 99)
        nums=[x["number"] for x in race["results"]]
        race["status"] = ("results_recorded" if len(nums) in (7,9) and len(nums)==len(set(nums))
                          else "results_partial" if nums else "entry_only")
        race["expectedCount"] = len(race["entries"]) or len(nums)
    board["races"] = sorted(by_key.values(), key=lambda x:(x["date"],x["track"],x["race"]))
    board["summary"]={"races":len(board["races"]),
        "entries":sum(len(x["entries"]) for x in board["races"]),
        "resultRows":sum(len(x["results"]) for x in board["races"])}
    return board

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="Offline fresh-intake merge check")
    parser.add_argument("--entries-fixture", help="JSON array-of-rows for local testing")
    parser.add_argument("--results-fixture", help="JSON array-of-rows for local testing")
    parser.add_argument("--out", default="daily-board-feed-v1.json")
    parser.add_argument("--date", default=datetime.now(JST).date().isoformat())
    args = parser.parse_args()
    today = datetime.strptime(args.date, "%Y-%m-%d").date()
    if args.self_test:
        entry_header=["開催日","場コード","競輪場","R","級班","車番","選手名","府県","期別","発走前ライン","元URL","取得日時JST","収集状態","レースキー","ソースID"]
        result_header=["開催日","場コード","競輪場","R","級班","車番","選手名","府県","期別","着順原文","決まり手","個人状況・例外","元URL","取得日時JST","レースキー"]
        entry=["2026-11-23","26","西武園","1","A3","1","テスト選手A","埼玉","100","","https://example.org/entry","2026-11-23 07:00 JST","取得済","2026-11-23|26|1","offline-test"]
        result=["2026-11-23","26","西武園","1","A3","1","テスト選手A","埼玉","100","1","差し","","https://example.org/result","2026-11-23 15:00 JST","2026-11-23|26|1"]
        test_day=datetime.strptime("2026-11-23","%Y-%m-%d").date()
        out=merge_new(build([["header"]*15],[["header"]*23],test_day),
                      [entry_header,entry],[result_header,result],test_day)
        r=out["races"]
        assert len(r)==1 and len(r[0]["entries"])==1 and len(r[0]["results"])==1
        assert r[0]["status"]=="results_partial" and out["sourceLatest"]["entries"]=="2026-11-23"
        print("SELF_TEST_OK: daily entry/result source merge; no live data or Sheets modified")
        return
    if bool(args.entries_fixture) != bool(args.results_fixture):
        raise ValueError("Provide both fixture files")
    if args.entries_fixture:
        entries = json.loads(Path(args.entries_fixture).read_text(encoding="utf8"))
        results = json.loads(Path(args.results_fixture).read_text(encoding="utf8"))
        fresh_entries = [list(["開催日","場コード","競輪場","R","級班","車番","選手名","府県","期別","発走前ライン","元URL","取得日時JST","収集状態","レースキー","ソースID"])]
        fresh_results = [list(["開催日","場コード","競輪場","R","級班","車番","選手名","府県","期別","着順原文","決まり手","個人状況・例外","元URL","取得日時JST","レースキー"])]
    else:
        entries, results, fresh_entries, fresh_results = fetch_sheets()
    out = merge_new(build(entries, results, today), fresh_entries, fresh_results, today)
    # No clock timestamp: reruns on unchanged source and date do not create commits.
    content = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    target = Path(args.out)
    if target.exists() and target.read_text(encoding="utf8") == content:
        print("UNCHANGED: daily board snapshot is identical")
        return
    target.write_text(content, encoding="utf8")
    print("DAILY_FEED races=%d entries=%d result_rows=%d latest_entries=%s latest_results=%s" %
          (out["summary"]["races"], out["summary"]["entries"], out["summary"]["resultRows"],
           out["sourceLatest"]["entries"], out["sourceLatest"]["results"]))
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ABORT daily feed: " + str(e), file=sys.stderr)
        sys.exit(1)
