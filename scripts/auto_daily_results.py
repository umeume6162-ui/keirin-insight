#!/usr/bin/env python3
"""Conservative current-day results collection from Google daily entry records.

Only complete 7/9-car races already in KI｜日次出走表 are eligible.
netkeirin + Chariloto observations must match in all result fields AND
each rider identity must match the stored pre-race entry. These observations
remain UNVERIFIED, never formal PASS. Each race is saved separately;
incomplete sources and mismatches are logged as hold/no write.
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from collect_historical_pair import collect
from compare_race_results import normalized_name, canonical_method
from upsert_daily_sheets import (
    SHEET_ID, HEADERS, CONFIG, apply, remote_client
)
from auto_daily_tospo_intake import verify_approved_editor

JST = ZoneInfo("Asia/Tokyo")

# Evidence-scoped source display differences; do not generalize all kanji.
PREFECTURE_ALIASES = {"神奈": "神奈川", "北海": "北海道", "鹿児": "鹿児島"}
RIDER_NAME_ALIASES = {"国井裕樹": "國井裕樹"}


def canonical_rider_name(value):
    value = normalized_name(value)
    return RIDER_NAME_ALIASES.get(value, value)


def canonical_prefecture(value):
    value = clean(value)
    return PREFECTURE_ALIASES.get(value, value)




def clean(value):
    return unicodedata.normalize("NFKC", str(value if value is not None else "")).strip()


def read_existing():
    session, token = remote_client()
    base = "https://sheets.googleapis.com/v4/spreadsheets/" + SHEET_ID + "/values:batchGet"
    query = [("ranges", "'" + CONFIG[key][0] + "'!A1:O10000") for key in CONFIG]
    response = session.get(base, params=query,
                           headers={"Authorization": "Bearer " + token}, timeout=40)
    response.raise_for_status()
    values = response.json().get("valueRanges", [])
    if len(values) != 2:
        raise ValueError("Missing daily Sheets tables")
    for i, kind in enumerate(CONFIG):
        rows = values[i].get("values", [])
        if not rows or rows[0] != HEADERS[kind]:
            raise ValueError("Daily sheet header mismatch: " + kind)
    return values[0]["values"][1:], values[1]["values"][1:]


def eligible_races(entries, results, start, end):
    existing = set()
    for row in results:
        if len(row) > 14 and row[14]:
            existing.add(clean(row[14]))
    groups = defaultdict(list)
    for row in entries:
        if len(row) < 9:
            continue
        day, code, track, race = map(clean, row[:4])
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d").date()
            if not (start <= parsed <= end):
                continue
            if not (code.isdigit() and 1 <= int(code) <= 99
                    and race.isdigit() and 1 <= int(race) <= 12):
                continue
        except ValueError:
            continue
        key = f"{day}|{int(code):02d}|{int(race)}"
        groups[key].append(row)
    eligible = []
    for key, rows in sorted(groups.items()):
        if key in existing or len(rows) not in (7, 9):
            continue
        numbers = [clean(r[5]) for r in rows]
        if sorted(numbers) != [str(i) for i in range(1, len(rows) + 1)]:
            continue
        tracks = {clean(r[2]) for r in rows}
        classes = {clean(r[4]) for r in rows}
        if len(tracks) != 1 or len(classes) != 1 or "" in tracks or "" in classes:
            continue
        eligible.append((key, rows))
    return eligible


def candidate(key, rows, collect_fn=collect):
    day, code, race = key.split("|")
    track, cls = clean(rows[0][2]), clean(rows[0][4])
    observation = collect_fn(day, code, track, int(race), cls, len(rows))
    comparison = observation["comparison"]
    if (comparison["raceKey"] != key or
            comparison["status"] != "SOURCE_CONTENT_MATCH_INDEPENDENCE_PENDING" or
            comparison["disagreements"] or comparison["formalPass"] is not False):
        raise ValueError("Two result publications do not agree")
    snapshots = {int(r[5]): r for r in rows}
    left = observation["observations"][0]
    payload = []
    capture = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    for source in left["results"]:
        number = int(source["number"])
        old = snapshots[number]
        if (canonical_rider_name(old[6]) != canonical_rider_name(source["name"])
                or canonical_prefecture(old[7]) != canonical_prefecture(source["prefecture"])
                or clean(old[8]).removesuffix("期") != clean(source["period"]).removesuffix("期")):
            raise ValueError("Rider identity does not match pre-race sheet")
        payload.append(dict(date=day, trackCode=code, track=track, race=int(race),
                            className=cls, number=number, name=old[6],
                            prefecture=old[7], period=old[8],
                            finish=source["finish"], method=canonical_method(source["method"]),
                            exception=source["exception"], sourceUrl=left["sourceUrl"],
                            capturedAt=capture))
    if len(payload) != len(rows):
        raise ValueError("Incomplete pair result")
    return {"entries": [], "results": payload,
            "sourceNote": "Content matched on two sites, upstream independence not verified"}


def process(entries, results, start, end, limit=4, write=False,
            collect_fn=collect, apply_fn=apply):
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    selected = eligible_races(entries, results, start, end)[:limit]
    reports = []
    for key, rows in selected:
        item = {"raceKey": key, "saved": False}
        try:
            data = candidate(key, rows, collect_fn=collect_fn)
            dry = apply_fn(data, dry_run=True)
            result_delta = dry["summary"]["results"]
            if (result_delta["new"] != len(rows) or result_delta["changed"] != 0 or
                    dry["summary"]["entries"]["new"] or
                    dry["summary"]["entries"]["changed"]):
                item["status"] = "SHEETS_DIFFERENCE_REVIEW_NO_WRITE"
            elif write:
                verify_approved_editor()
                saved = apply_fn(data, dry_run=False)
                if (saved["summary"]["results"]["new"] != len(rows) or
                        saved["summary"]["results"]["changed"] != 0):
                    raise RuntimeError("Saved result row count differs from dry-run")
                item.update(status="SAVED_UNVERIFIED_RESULTS", saved=True,
                            cars=len(rows))
            else:
                item.update(status="DRY_RUN_TWO_SOURCES_MATCH", cars=len(rows))
        except Exception as exc:
            item.update(status="SOURCE_OR_IDENTITY_REVIEW_NO_WRITE",
                        errorType=type(exc).__name__)
        reports.append(item)
    return {"schema": "ki-daily-result-intake-v1", "formalPass": False,
            "eligibleExamined": len(selected), "results": reports}


def self_test():
    day = "2026-11-23"
    records = [[day, "26", "西武園", "1", "A3", str(n),
                f"選手 {n}", "埼玉", "93"] for n in range(1, 8)]
    keys = eligible_races(records, [], datetime.strptime(day, "%Y-%m-%d").date(),
                          datetime.strptime(day, "%Y-%m-%d").date())
    assert len(keys) == 1
    assert canonical_rider_name("国井 裕樹") == canonical_rider_name("國井裕樹")
    assert canonical_prefecture("神奈") == canonical_prefecture("神奈川")
    assert canonical_rider_name("国井裕樹") != canonical_rider_name("國村洋")
    race_data = dict(date=day, trackCode="26", track="西武園",
                     race=1, className="A3", expectedCars=7)
    riders = [dict(number=n, name=f"選手 {n}", prefecture="埼玉",
                   period="93", finish=str(n), method="差" if n == 1 else "",
                   exception="") for n in range(1, 8)]
    left = dict(sourceUrl="https://keirin.netkeiba.com/race/result/?race_id=202611232601",
                sourceId="netkeirin-result", race=race_data, results=riders)
    right = dict(sourceUrl="https://www.chariloto.com/keirin/results/26/2026-11-23",
                 sourceId="chariloto-day-results", race=race_data, results=riders)
    from compare_race_results import compare
    actual = {"observations": [left, right], "comparison": compare({"observations": [left, right]})}
    calls = []
    def pretend_apply(data, dry_run=True):
        calls.append(dry_run)
        return {"summary": {"entries": {"new": 0, "changed": 0},
                            "results": {"new": 7, "changed": 0}}}
    start = datetime.strptime(day, "%Y-%m-%d").date()
    summary = process(records, [], start, start, collect_fn=lambda *a: actual,
                      apply_fn=pretend_apply)
    assert summary["results"][0]["status"] == "DRY_RUN_TWO_SOURCES_MATCH" and calls == [True]
    broken = [list(x) for x in records]
    broken[0][6] = "別人"
    summary = process(broken, [], start, start, collect_fn=lambda *a: actual,
                      apply_fn=pretend_apply)
    assert summary["results"][0]["status"] == "SOURCE_OR_IDENTITY_REVIEW_NO_WRITE"
    assert calls == [True]
    assert eligible_races(records, [[""] * 14 + ["2026-11-23|26|1"]], start, start) == []
    print("SELF_TEST_OK: seven-car two-source result intake, identity guard and duplicate skip")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--date", help="Optional exact event date YYYY-MM-DD")
    p.add_argument("--max-races", type=int, default=4)
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    today = datetime.now(JST).date()
    if args.date:
        fixed = datetime.strptime(args.date, "%Y-%m-%d").date()
        if fixed > today:
            raise ValueError("Cannot collect future results")
        start = end = fixed
    else:
        start, end = today - timedelta(days=1), today
    entries, results = read_existing()
    report = process(entries, results, start, end, limit=args.max_races, write=args.apply)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("DAILY_RESULT_ABORT: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
