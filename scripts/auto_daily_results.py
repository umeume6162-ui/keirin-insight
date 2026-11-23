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
import time
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


def select_rotating_races(eligible, limit, now=None):
    """Spread bounded attempts across eligible races instead of retrying the first N.

    Four scheduled daily runs use different five-hour windows (07/12/17/22 JST).
    Rotate without wrapping within a single attempt; a later run gets the next
    block, including when an earlier source remains unavailable.
    """
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    if not eligible:
        return []
    now = now or datetime.now(JST)
    # The schedule runs at 07:10, 12:10, 17:10 and 22:10 JST.
    slot = ((now.hour - 7) % 24) // 5
    blocks = (len(eligible) + limit - 1) // limit
    index = ((now.date().toordinal() * 4) + slot) % blocks
    first = index * limit
    return eligible[first:first + limit]


def process(entries, results, start, end, limit=4, write=False,
            collect_fn=collect, apply_fn=apply, max_seconds=720,
            monotonic_fn=time.monotonic):
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    if not 60 <= max_seconds <= 1800:
        raise ValueError("max_seconds must be 60..1800")
    started = monotonic_fn()
    eligible = eligible_races(entries, results, start, end)
    selected = select_rotating_races(eligible, limit)
    reports = []
    for key, rows in selected:
        if monotonic_fn() - started >= max_seconds:
            break
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
            "eligibleTotal": len(eligible), "eligibleExamined": len(reports),
            "eligibleDeferred": len(eligible) - len(reports),
            "timeBudgetExceeded": len(reports) < len(selected),
            "savedCount": sum(bool(r["saved"]) for r in reports),
            "results": reports}


def self_test():
    day = "2026-11-23"
    records = [[day, "26", "西武園", "1", "A3", str(n),
                f"選手 {n}", "埼玉", "93"] for n in range(1, 8)]
    keys = eligible_races(records, [], datetime.strptime(day, "%Y-%m-%d").date(),
                          datetime.strptime(day, "%Y-%m-%d").date())
    assert len(keys) == 1
    # A race missed several days ago must remain eligible for the bounded retry.
    older = [list(row) for row in records]
    older_day = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=6)).date()
    for row in older:
        row[0] = older_day.isoformat()
    assert len(eligible_races(older, [], older_day, start_day := datetime.strptime(day, "%Y-%m-%d").date())) == 1
    assert eligible_races(older, [], older_day + timedelta(days=1), start_day) == []
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
    assert (summary["eligibleTotal"], summary["eligibleExamined"], summary["eligibleDeferred"], summary["savedCount"]) == (1, 1, 0, 0)
    broken = [list(x) for x in records]
    broken[0][6] = "別人"
    summary = process(broken, [], start, start, collect_fn=lambda *a: actual,
                      apply_fn=pretend_apply)
    assert summary["results"][0]["status"] == "SOURCE_OR_IDENTITY_REVIEW_NO_WRITE"
    assert calls == [True]
    assert eligible_races(records, [[""] * 14 + ["2026-11-23|26|1"]], start, start) == []
    # Repeated source failures at the start of the backlog must not starve later races.
    rotation = [(f"race-{i}", []) for i in range(13)]
    day0 = datetime(2026, 11, 23, 7, 10, tzinfo=JST)
    batches = [select_rotating_races(rotation, 4, day0.replace(hour=h))
               for h in (7, 12, 17, 22)]
    assert all(1 <= len(batch) <= 4 for batch in batches)
    assert len({k for batch in batches for k, _ in batch}) == 13
    # The production limit is twelve races; verify the four JST windows
    # eventually cover every candidate even when the backlog spans days.
    from datetime import timedelta
    for count in (12, 13, 48, 49, 80):
        candidates = [(f"race-{i}", []) for i in range(count)]
        covered = set()
        for offset in range(6):
            for hour in (7, 12, 17, 22):
                moment = (day0 + timedelta(days=offset)).replace(hour=hour)
                covered.update(key for key, _ in select_rotating_races(candidates, 12, moment))
        assert covered == {key for key, _ in candidates}, count
    assert select_rotating_races([], 4) == []
    exhausted = process(records, [], start, start, collect_fn=lambda *a: actual,
                        apply_fn=pretend_apply, max_seconds=60,
                        monotonic_fn=iter((0, 61)).__next__)
    assert exhausted["eligibleExamined"] == 0 and exhausted["eligibleDeferred"] == 1
    assert exhausted["timeBudgetExceeded"] and exhausted["savedCount"] == 0
    assert [k for k, _ in select_rotating_races(rotation, 4, day0)] == [
        k for k, _ in select_rotating_races(rotation, 4, day0)]
    print("SELF_TEST_OK: seven-car two-source result intake, identity guard and duplicate skip")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--date", help="Optional exact event date YYYY-MM-DD")
    p.add_argument("--max-races", type=int, default=4)
    p.add_argument("--max-seconds", type=int, default=720)
    p.add_argument("--lookback-days", type=int, default=7,
                   help="Include current date and this many previous event dates (1..14)")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not 1 <= args.lookback_days <= 14:
        raise ValueError("lookback-days must be 1..14")
    today = datetime.now(JST).date()
    if args.date:
        fixed = datetime.strptime(args.date, "%Y-%m-%d").date()
        if fixed > today:
            raise ValueError("Cannot collect future results")
        start = end = fixed
    else:
        start, end = today - timedelta(days=args.lookback_days), today
    entries, results = read_existing()
    report = process(entries, results, start, end, limit=args.max_races,
                     write=args.apply, max_seconds=args.max_seconds)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("DAILY_RESULT_ABORT: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
