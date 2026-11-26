#!/usr/bin/env python3
"""Build the DAILY viewing feed from existing Sheets, without changing V99 or verified data."""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
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
              ("ranges", "'KI｜日次出走表'!A1:O"),
              ("ranges", "'KI｜日次結果'!A1:O")]
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

def merge_new(board, entry_values, result_values, today, *, window=None):
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
    start, end = window or (today - timedelta(days=2), today + timedelta(days=2))
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
            race_key = f"{r[0]}|{r[1]}|{int(r[3])}"
            intake_key = r[13] if kind == "entries" else r[14]
            daily_intake = bool(re.fullmatch(r"[0-9]{2}", r[1]) and race_key == intake_key)
            if daily_intake:
                if item.get("trackCode", r[1]) != r[1]:
                    raise ValueError(f"Conflicting venue codes for {key}")
                item["trackCode"] = r[1]
            if kind == "entries":
                item["entrySource"] = "KI｜日次出走表"
                values = {"number":int(r[5]),"name":r[6],"prefecture":r[7] or None,
                          "period":r[8] or None,"preRaceLine":r[9] or None,
                          "position":None,"capturedAt":r[11] or None,
                          "sourceUrl":r[10] or None,"dailyIntake":daily_intake}
            else:
                item["resultSource"] = "KI｜日次結果"
                values = {"number":int(r[5]),"name":r[6],"prefecture":r[7] or None,
                          "period":r[8] or None,"finish":r[9],
                          "method":r[10] or None,"exception":r[11] or None,
                          "sourceUrl":r[12] or None,"capturedAt":r[13] or None,"dailyIntake":daily_intake}
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

DAILY_VERIFICATION = "source_sheet_unverified_do_not_treat_as_formal_PASS"


def archive_phase(captured_at, race):
    """Eligibility uses the published start and a parseable observation time."""
    try:
        captured = datetime.strptime(captured_at, "%Y-%m-%d %H:%M JST")
        start = datetime.fromisoformat(f"{race['date']}T{race['startTime']}")
        return "preRace" if captured < start else "atOrAfterStart"
    except (TypeError, ValueError, KeyError):
        return "unknown"


def merge_history_race(old, race):
    if old and old["key"] != race["key"]:
        raise ValueError("Archive race key changed")
    saved = dict(old or race)
    for field in ("startTime", "startTimeSourceUrl", "session", "timeSlot"):
        if not saved.get(field) and race.get(field):
            saved[field] = race[field]
    for kind in ("entries", "results"):
        rows = {row["number"]: row for row in (old or {}).get(kind, [])}
        for row in race[kind]:
            snapshot = {k: v for k, v in row.items() if k not in ("riderStats", "dailyIntake")}
            rows.setdefault(row["number"], snapshot)
        order = (lambda row: row["number"]) if kind == "entries" else (
            lambda row: (int(row["finish"]) if str(row["finish"]).isdigit() else 99, row["number"])
        )
        saved[kind] = sorted(rows.values(), key=order)
    saved["entryPhases"] = {
        str(row["number"]): archive_phase(row.get("capturedAt"), saved) for row in saved["entries"]
    }

    entry_identity = lambda row: (row["number"], "".join(row["name"].split()), row["prefecture"], row["period"])
    identity_matches = list(map(entry_identity, saved["entries"])) == list(map(entry_identity, race["entries"]))
    for field, captured, values in (
        ("statSnapshots", (race.get("riderStatsSource") or {}).get("capturedAt"),
         {"source": race.get("riderStatsSource"),
          "byCar": {str(row["number"]): row["riderStats"] for row in race["entries"] if row.get("riderStats")}}),
        ("lineSnapshots", race.get("lineCapturedAt"),
         {"sourceUrl": race.get("lineSourceUrl"), "capturedAt": race.get("lineCapturedAt"),
          "byCar": {str(row["number"]): row["preRaceLine"] for row in race["entries"] if row.get("preRaceLine")}}),
    ):
        if identity_matches and captured and values["byCar"]:
            saved.setdefault(field, {}).setdefault(archive_phase(captured, saved), values)

    # The original per-car rows are kept. Enrichment is carried in its own
    # observation with its source and time, and never inherits the card's time.
    for field in ("riderStatsSource", "lineSourceUrl", "lineCapturedAt"):
        saved.pop(field, None)
    saved["expectedCount"] = len(saved["entries"])
    cars = {row["number"] for row in saved["entries"]}
    result_cars = {row["number"] for row in saved["results"]}
    saved["status"] = (
        "results_recorded" if len(cars) in (7, 9) and result_cars == cars
        else "results_partial" if result_cars else "entry_only"
    )
    return saved


def archive_board(board, directory):
    if board["schema"] != "ki-daily-board-v1" or board["verification"] != DAILY_VERIFICATION:
        raise ValueError("Invalid daily board for archive")
    by_day = defaultdict(list)
    for race in board["races"]:
        code = race.get("trackCode")
        if not code or not re.fullmatch(r"[0-9]{2}", code):
            continue  # Legacy viewing fallback has no confirmed venue code.
        day = date.fromisoformat(race["date"]).isoformat()
        key = f"{day}|{code}|{race['race']}"
        entries = [row for row in race["entries"] if row.get("dailyIntake")]
        results = [row for row in race["results"] if row.get("dailyIntake")]
        if entries or results:
            by_day[day].append(dict(race, key=key, entries=entries, results=results))

    directory.mkdir(parents=True, exist_ok=True)
    changed = 0
    for day, races in by_day.items():
        target = directory / f"{day}.json"
        existing = json.loads(target.read_text(encoding="utf8")) if target.exists() else None
        if existing and (existing["schema"] != "ki-daily-history-v1" or existing["date"] != day
                         or existing["verification"] != DAILY_VERIFICATION):
            raise ValueError(f"Unexpected data in {target}")
        by_key = {r["key"]: r for r in existing["races"]} if existing else {}
        for race in races:
            by_key[race["key"]] = merge_history_race(by_key.get(race["key"]), race)
        payload = {"schema": "ki-daily-history-v1", "date": day, "verification": DAILY_VERIFICATION,
                   "races": sorted(by_key.values(), key=lambda race: (race["trackCode"], race["race"]))}
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        if not target.exists() or target.read_text(encoding="utf8") != content:
            temp = target.with_suffix(".tmp")
            temp.write_text(content, encoding="utf8")
            temp.replace(target)
            changed += 1
    return changed


def carryover_board(entries, results, today):
    """Reuse daily intake from the result retry window before the display window."""
    start, end = today - timedelta(days=7), today - timedelta(days=3)
    board = {"schema": "ki-daily-board-v1", "verification": DAILY_VERIFICATION,
             "sourceLatest": {"entries": None, "results": None}, "races": []}
    return merge_new(board, entries, results, today, window=(start, end))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="Offline fresh-intake merge check")
    parser.add_argument("--entries-fixture", help="JSON array-of-rows for local testing")
    parser.add_argument("--results-fixture", help="JSON array-of-rows for local testing")
    parser.add_argument("--out", default="daily-board-feed-v1.json")
    parser.add_argument("--archive", type=Path, help="Archive the existing enriched --out instead of fetching Sheets")
    parser.add_argument("--archive-carryover", type=Path,
                        help="Write/read job-local intake outside the display window")
    parser.add_argument("--date", default=datetime.now(JST).date().isoformat())
    args = parser.parse_args()
    today = datetime.strptime(args.date, "%Y-%m-%d").date()
    if args.archive:
        board = json.loads(Path(args.out).read_text(encoding="utf8"))
        if args.archive_carryover:
            carryover = json.loads(args.archive_carryover.read_text(encoding="utf8"))
            if (carryover["schema"] != board["schema"]
                    or carryover["verification"] != board["verification"]
                    or any(race["date"] >= board["windowStart"] for race in carryover["races"])):
                raise ValueError("Invalid carryover archive input")
            board["races"].extend(carryover["races"])
        print(f"DAILY_HISTORY_CHANGED_DAYS={archive_board(board, args.archive)}")
        return
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
        assert r[0]["trackCode"] == "26" and r[0]["results"][0]["capturedAt"] == result[13]
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            archived = Path(tmp)
            assert archive_board(out, archived) == 1
            assert archive_board(out, archived) == 0
            race = r[0]
            race["startTime"] = "14:00"
            race["entries"][0]["name"] = "後日の名前"
            assert archive_board(out, archived) == 1
            race["entries"][0]["name"] = entry[6]
            race["entries"][0]["riderStats"] = {"score": "75"}
            race["riderStatsSource"] = {"capturedAt": "2026-11-23 15:00 JST", "period": "直近4か月"}
            assert archive_board(out, archived) == 1
            race["entries"][0]["riderStats"] = {"score": "70"}
            race["riderStatsSource"]["capturedAt"] = "2026-11-23 13:00 JST"
            assert archive_board(out, archived) == 1
            saved = json.loads((archived / "2026-11-23.json").read_text())["races"][0]
            assert saved["key"] == "2026-11-23|26|1" and saved["entries"][0]["name"] == entry[6]
            assert saved["statSnapshots"]["preRace"]["byCar"]["1"]["score"] == "70"
            assert saved["statSnapshots"]["atOrAfterStart"]["byCar"]["1"]["score"] == "75"
            assert archive_board(dict(out, races=[]), archived) == 0
            # A result recovered after the display window must still append to
            # history, using the original pre-race record already on disk.
            original = dict(out, races=[dict(race, results=[])])
            carry_dir = archived / "carryover"
            assert archive_board(original, carry_dir) == 1
            later = test_day + timedelta(days=3)
            carry = carryover_board([entry_header, entry], [result_header, result], later)
            assert carry["races"][0]["results"][0]["capturedAt"] == result[13]
            assert archive_board(carry, carry_dir) == 1
            assert archive_board(carry, carry_dir) == 0
            assert not carryover_board([entry_header, entry], [result_header, result],
                                       test_day + timedelta(days=8))["races"]
        print("SELF_TEST_OK: daily merge and immutable daily history; no live data or Sheets modified")
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
    if args.archive_carryover:
        carryover = carryover_board(fresh_entries, fresh_results, today)
        args.archive_carryover.write_text(json.dumps(carryover, ensure_ascii=False), encoding="utf8")
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
