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
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from collect_historical_pair import collect
from result_hold_diagnostics import classify_result_hold, review_route
from compare_race_results import normalized_name, canonical_method
from upsert_daily_sheets import (
    SHEET_ID, HEADERS, CONFIG, apply, remote_client
)
from auto_daily_tospo_intake import verify_approved_editor
from enrich_daily_start_times import source_identity

JST = ZoneInfo("Asia/Tokyo")

# Evidence-scoped source display differences; do not generalize all kanji.
PREFECTURE_ALIASES = {"神奈": "神奈川", "北海": "北海道", "鹿児": "鹿児島"}
RIDER_NAME_ALIASES = {"国井裕樹": "國井裕樹", "斎藤輝彦": "齋藤輝彦"}


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
    query = [("ranges", "'" + CONFIG[key][0] + "'!A1:O") for key in CONFIG]
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
        # A1/A2 and S1/S2 are rider grades, not proof of different races.
        # They legitimately coexist in one A- or S-class event.
        permitted_groups = ({"A1", "A2"}, {"S1", "S2", "SS"}, {"A3"}, {"L1", "L2"})
        if (len(tracks) != 1 or "" in tracks or "" in classes or
                not any(classes <= group for group in permitted_groups)):
            continue
        eligible.append((key, rows))
    return eligible



def partial_existing_results(entries, results, start, end):
    """Report incomplete/duplicate stored results; never overwrite them automatically."""
    available = dict(eligible_races(entries, [], start, end))
    by_key = defaultdict(list)
    for row in results:
        if len(row) > 14:
            key = clean(row[14])
            if key in available:
                by_key[key].append(row)
    findings = []
    for key, stored in sorted(by_key.items()):
        expected_rows = available[key]
        expected = {str(i) for i in range(1, len(expected_rows) + 1)}
        numbers = [clean(row[5]) if len(row) > 5 else "" for row in stored]
        expected_by_car = {clean(row[5]): row for row in expected_rows}
        bad_cars = []
        for row in stored:
            number = clean(row[5]) if len(row) > 5 else ""
            original = expected_by_car.get(number)
            # Result rows must retain date/venue/race/class and rider identity.
            if original is None or len(row) < 9 or any((
                clean(row[i]) != clean(original[i]) for i in (0, 1, 2, 3, 4)
            )) or (canonical_rider_name(row[6]) != canonical_rider_name(original[6])
                   or canonical_prefecture(row[7]) != canonical_prefecture(original[7])
                   or clean(row[8]).removesuffix("期")
                   != clean(original[8]).removesuffix("期")):
                bad_cars.append(number)
        stored_set = set(numbers)
        missing = sorted(expected - stored_set, key=int)
        unexpected = sorted(stored_set - expected)
        duplicate = sorted((n for n in stored_set if numbers.count(n) > 1))
        if missing or unexpected or duplicate or bad_cars or len(numbers) != len(expected):
            findings.append({"raceKey": key, "expectedCars": len(expected),
                             "storedRows": len(stored),
                             "missingCarNumbers": missing,
                             "unexpectedCarNumbers": unexpected,
                             "duplicateCarNumbers": duplicate,
                             "identityMismatchCars": sorted(set(bad_cars)),
                             "status": "PARTIAL_DUPLICATE_OR_IDENTITY_CONFLICT_REVIEW"})
    return findings



def safe_missing_result_payload(candidate_payload, stored_rows, entry_rows):
    """Return only absent cars after proving every stored observation matches.

    Existing rows are never sent to the upsert writer. Partial results with
    duplicated cars, altered rider identity, or conflicting finishes are held.
    """
    if not stored_rows:
        raise ValueError("No partial stored results to complete")
    desired = {str(x["number"]): x for x in candidate_payload["results"]}
    if len(desired) != len(entry_rows) or len(candidate_payload["results"]) != len(entry_rows):
        raise ValueError("Candidate full-field result mismatch")
    stored_numbers = []
    expected_key = f"{clean(entry_rows[0][0])}|{int(clean(entry_rows[0][1])):02d}|{int(clean(entry_rows[0][3]))}"
    for row in stored_rows:
        if len(row) < 15 or not clean(row[5]) or clean(row[14]) != expected_key:
            raise ValueError("Partial stored result identity mismatch")
        number = clean(row[5])
        if number in stored_numbers or number not in desired:
            raise ValueError("Duplicate or unexpected stored result car")
        stored_numbers.append(number)
        proposed = desired[number]
        values = [proposed["date"], proposed["trackCode"], proposed["track"],
                  str(proposed["race"]), proposed["className"], str(proposed["number"]),
                  proposed["name"], proposed["prefecture"], proposed["period"],
                  proposed["finish"], proposed["method"], proposed["exception"]]
        # Exact normalized comparison for all data, allowing documented
        # source-specific rider naming variants but not a changed finish.
        for pos in range(12):
            old, new = clean(row[pos]), clean(values[pos])
            if pos == 6:
                equal = canonical_rider_name(old) == canonical_rider_name(new)
            elif pos == 7:
                equal = canonical_prefecture(old) == canonical_prefecture(new)
            elif pos == 8:
                equal = old.removesuffix("期") == new.removesuffix("期")
            elif pos == 10:
                equal = canonical_method(old) == canonical_method(new)
            else:
                equal = old == new
            if not equal:
                raise ValueError("Stored partial result conflicts with two-source full field")
    missing = [x for x in candidate_payload["results"]
               if str(x["number"]) not in stored_numbers]
    if not missing:
        raise ValueError("No genuinely missing result cars")
    return {"entries": [], "results": missing}



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
                            className=old[4], number=number, name=old[6],
                            prefecture=old[7], period=old[8],
                            finish=source["finish"], method=canonical_method(source["method"]),
                            exception=source["exception"], sourceUrl=left["sourceUrl"],
                            capturedAt=capture))
    if len(payload) != len(rows):
        raise ValueError("Incomplete pair result")
    second_source = observation["observations"][1]["sourceId"]
    if second_source not in ("chariloto-day-results", "lotoplace-day-results"):
        raise ValueError("Unexpected second result source")
    return {"entries": [], "results": payload,
            "sourcePairMode": observation.get("sourcePairMode", "NETKEIRIN_DAY_RESULTS"),
            "sourceNote": ("Content matched on two sites, upstream independence not verified; "
                           "secondSourceId=" + second_source)}





def due_result_races(eligible, cache, now=None):
    """Keep today's races out of result intake until their sourced start time + 20m.

    Unknown or stale start-time evidence is deliberately not treated as race
    completion. Yesterday and older races remain eligible without this gate.
    """
    if cache.get("schema") != "ki-daily-start-times-v1" or not isinstance(cache.get("races"), dict):
        raise ValueError("Invalid start-time cache")
    now = now or datetime.now(JST)
    due, withheld = [], []
    for key, rows in eligible:
        day, code, number = key.split("|")
        if day < now.date().isoformat():
            due.append((key, rows))
            continue
        if day > now.date().isoformat():
            withheld.append(key)
            continue
        track = clean(rows[0][2])
        # Bind cached times to the identical original racecard source and rider list.
        race = {"key": f"{day}|{track}|{int(number)}", "date": day,
                "track": track, "race": int(number),
                "entries": [{"number": int(row[5]), "name": clean(row[6]),
                             "sourceUrl": clean(row[10]) if len(row) > 10 else ""}
                            for row in rows]}
        ident = source_identity(race)
        saved = cache["races"].get(race["key"])
        if not ident or not isinstance(saved, dict) or (
                saved.get("sourceUrl"), saved.get("signature")) != ident:
            withheld.append(key)
            continue
        start_time = saved.get("startTime")
        if not isinstance(start_time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start_time):
            withheld.append(key)
            continue
        target = datetime.strptime(f"{day} {start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        if now >= target + timedelta(minutes=20):
            due.append((key, rows))
        else:
            withheld.append(key)
    return due, withheld


def load_start_time_cache(path="daily-race-start-times-v1.json"):
    source = Path(path)
    if not source.is_file():
        return {"schema": "ki-daily-start-times-v1", "races": {}}
    return json.loads(source.read_text(encoding="utf-8"))



def select_rotating_races(eligible, limit, now=None):
    """Spread bounded attempts across eligible races instead of retrying the first N.

    Five scheduled daily runs use distinct 00/07/12/17/22 JST slots.
    Rotate without wrapping within a single attempt; a later run gets the next
    block, including when an earlier source remains unavailable.
    """
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    if not eligible:
        return []
    now = now or datetime.now(JST)
    # Explicitly account for the post-midnight 00:10 run.
    # No two configured runs share a slot on the same JST date.
    slot = (0 if now.hour < 7 else 1 if now.hour < 12 else
            2 if now.hour < 17 else 3 if now.hour < 22 else 4)
    blocks = (len(eligible) + limit - 1) // limit
    index = ((now.date().toordinal() * 5) + slot) % blocks
    first = index * limit
    return eligible[first:first + limit]


def process(entries, results, start, end, limit=4, write=False,
            collect_fn=collect, apply_fn=apply, max_seconds=720,
            monotonic_fn=time.monotonic, start_times=None, now=None):
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    if not 60 <= max_seconds <= 1800:
        raise ValueError("max_seconds must be 60..1800")
    started = monotonic_fn()
    eligible = eligible_races(entries, results, start, end)
    incomplete_stored = partial_existing_results(entries, results, start, end)
    # Only structurally partial results are candidates for guarded completion.
    available = dict(eligible_races(entries, [], start, end))
    by_stored = defaultdict(list)
    for stored_row in results:
        if len(stored_row) > 14 and clean(stored_row[14]) in available:
            by_stored[clean(stored_row[14])].append(stored_row)
    partial_candidates = []
    for flagged in incomplete_stored:
        key = flagged["raceKey"]
        if (flagged["missingCarNumbers"] and not flagged["unexpectedCarNumbers"]
                and not flagged["duplicateCarNumbers"] and
                not flagged["identityMismatchCars"] and key in available):
            partial_candidates.append((key, available[key]))
    all_due_candidates = sorted(eligible + partial_candidates)
    not_due = []
    due = all_due_candidates
    if start_times is not None:
        due, not_due = due_result_races(all_due_candidates, start_times, now=now)
    selected = select_rotating_races(due, limit, now=now)
    reports = []
    for key, rows in selected:
        if monotonic_fn() - started >= max_seconds:
            break
        item = {"raceKey": key, "saved": False}
        phase = "COLLECT_COMPARE"
        try:
            data = candidate(key, rows, collect_fn=collect_fn)
            was_partial = key in by_stored
            if was_partial:
                data = {**data, **safe_missing_result_payload(data, by_stored[key], rows)}
            expected_delta = len(data["results"])
            second_source = data["sourceNote"].rsplit("secondSourceId=", 1)[-1]
            item["sourcePairMode"] = data["sourcePairMode"]
            if second_source in ("chariloto-day-results", "lotoplace-day-results"):
                item["secondSourceId"] = second_source
                item["alternateSourceUsed"] = second_source == "lotoplace-day-results"
            phase = "SHEETS_DRY_RUN"
            dry = apply_fn(data, dry_run=True)
            result_delta = dry["summary"]["results"]
            if (result_delta["new"] != expected_delta or result_delta["changed"] != 0 or
                    dry["summary"]["entries"]["new"] or
                    dry["summary"]["entries"]["changed"]):
                item["status"] = "SHEETS_DIFFERENCE_REVIEW_NO_WRITE"
            elif write:
                phase = "SHEETS_APPLY"
                verify_approved_editor()
                saved = apply_fn(data, dry_run=False)
                if (saved["summary"]["results"]["new"] != expected_delta or
                        saved["summary"]["results"]["changed"] != 0):
                    raise RuntimeError("Saved result row count differs from dry-run")
                item.update(status="SAVED_UNVERIFIED_RESULTS", saved=True,
                            cars=expected_delta, partialCompleted=was_partial)
            else:
                item.update(status="DRY_RUN_TWO_SOURCES_MATCH", cars=expected_delta,
                            partialCompleted=was_partial)
        except Exception as exc:
            # Return only finite source stage/reason codes, never source HTML or
            # raw exception strings. Preserve original failure cause for routing.
            underlying = exc.__cause__ if getattr(exc, "source_stage", None) and exc.__cause__ else exc
            reason = classify_result_hold(underlying, phase)
            item.update(status="SOURCE_OR_IDENTITY_REVIEW_NO_WRITE",
                        errorType=type(underlying).__name__,
                        failurePhase=phase,
                        reasonCode=reason,
                        reviewRoute=review_route(reason))
            if getattr(exc, "source_stage", None) in (
                    "PRIMARY_NETKEIRIN", "SECONDARY_EXPLICIT",
                    "SECONDARY_BOTH_UNAVAILABLE", "ALTERNATE_PAIR_UNAVAILABLE"):
                item["sourceStage"] = exc.source_stage
        reports.append(item)
    return {"schema": "ki-daily-result-intake-v1", "formalPass": False,
            "eligibleTotal": len(all_due_candidates), "eligibleExamined": len(reports),
            "eligibleDeferred": len(all_due_candidates) - len(reports),
            "notYetDueCount": len(not_due), "notYetDueSample": not_due[:10],
            "timeBudgetExceeded": len(reports) < len(selected),
            "savedCount": sum(bool(r["saved"]) for r in reports),
            "partialExistingCount": len(incomplete_stored),
            "partialExisting": incomplete_stored,
            "results": reports}


def self_test():
    day = "2026-11-23"
    records = [[day, "26", "西武園", "1", "A3", str(n),
                f"選手 {n}", "埼玉", "93"] for n in range(1, 8)]
    keys = eligible_races(records, [], datetime.strptime(day, "%Y-%m-%d").date(),
                          datetime.strptime(day, "%Y-%m-%d").date())
    assert len(keys) == 1
    # Production-shape regression: Tamano A1/A2 races have mixed rider
    # grades, yet every rider must retain their own grade in the result row.
    mixed = [list(r) for r in records]
    for row in mixed:
        row[4] = "A2"
    for i in (1, 3, 5):
        mixed[i][4] = "A1"
    assert len(eligible_races(mixed, [], start := datetime.strptime(
        day, "%Y-%m-%d").date(), start)) == 1
    mixed_other = [list(r) for r in mixed]
    mixed_other[0][4] = "S1"
    assert eligible_races(mixed_other, [], start, start) == []
    s_mix = [list(r) for r in records]
    for i, row in enumerate(s_mix):
        row[4] = "S1" if i % 2 else "S2"
    assert len(eligible_races(s_mix, [], start, start)) == 1
    ss_mix = [list(r) for r in s_mix]
    ss_mix[0][4] = "SS"
    assert len(eligible_races(ss_mix, [], start, start)) == 1
    l_mix = [list(r) for r in records]
    for i, row in enumerate(l_mix):
        row[4] = "L1" if i % 2 else "L2"
    assert len(eligible_races(l_mix, [], start, start)) == 1
    # Nine-car S1/S2 races remain eligible, retaining every rider's own grade.
    nine = [list(r) for r in records] + [[day, "26", "西武園", "1", "S1", str(n),
            f"選手 {n}", "埼玉", "93"] for n in (8, 9)]
    for i, row in enumerate(nine[:7]):
        row[4] = "S2" if i % 2 else "S1"
    assert len(eligible_races(nine, [], start, start)) == 1
    assert eligible_races(nine[:-1], [], start, start) == []
    mixed_nine = [list(r) for r in nine]
    mixed_nine[8][4] = "A1"
    assert eligible_races(mixed_nine, [], start, start) == []
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
    mixed_result = candidate(day+"|26|1", mixed, collect_fn=lambda *a: actual)
    assert [r["className"] for r in mixed_result["results"]] == [r[4] for r in mixed]
    fallback_pair = {"observations": [
        {**left, "sourceId": "chariloto-day-results",
         "sourceUrl": "https://www.chariloto.com/keirin/results/26/2026-11-23"},
        {**right, "sourceId": "lotoplace-day-results",
         "sourceUrl": "https://www.lotoplace.jp/keirin/results/26/2026-11-23/"}
    ], "comparison": actual["comparison"],
       "sourcePairMode": "CHARILOTO_LOTOPLACE_FALLBACK"}
    fallback_candidate = candidate(day+"|26|1", records, collect_fn=lambda *a: fallback_pair)
    assert fallback_candidate["sourcePairMode"] == "CHARILOTO_LOTOPLACE_FALLBACK"
    assert "secondSourceId=lotoplace-day-results" in fallback_candidate["sourceNote"]
    calls = []
    def pretend_apply(data, dry_run=True):
        calls.append(dry_run)
        return {"summary": {"entries": {"new": 0, "changed": 0},
                            "results": {"new": 7, "changed": 0}}}
    start = datetime.strptime(day, "%Y-%m-%d").date()
    summary = process(records, [], start, start, collect_fn=lambda *a: actual,
                      apply_fn=pretend_apply)
    # Same-day source-bound gate: the race must have started 20 minutes ago.
    from enrich_daily_start_times import source_identity
    gate_rows = [list(row) + [""] * (11 - len(row)) for row in records]
    gate_url = "https://keirin.tokyo-sports.co.jp/list/race/test"
    for row in gate_rows:
        row[10] = gate_url
    gate_race = {"key": day+"|西武園|1", "date": day, "track": "西武園",
                 "race": 1, "entries": [{"number": int(row[5]),
                 "name": row[6], "sourceUrl": gate_url} for row in gate_rows]}
    signature = source_identity(gate_race)
    assert signature is not None
    cache = {"schema": "ki-daily-start-times-v1", "races": {
        gate_race["key"]: {"startTime": "20:57", "sourceUrl": gate_url,
                           "signature": signature[1]}}}
    before = datetime(2026, 11, 23, 19, 0, tzinfo=JST)
    assert due_result_races([(day+"|26|1", gate_rows)], cache, before)[0] == []
    at_start = datetime(2026, 11, 23, 20, 57, tzinfo=JST)
    assert due_result_races([(day+"|26|1", gate_rows)], cache, at_start)[0] == []
    after = datetime(2026, 11, 23, 21, 17, tzinfo=JST)
    assert len(due_result_races([(day+"|26|1", gate_rows)], cache, after)[0]) == 1
    stale = {"schema": cache["schema"], "races": {
        gate_race["key"]: {**cache["races"][gate_race["key"]], "signature": "wrong"}}}
    assert due_result_races([(day+"|26|1", gate_rows)], stale, after)[0] == []
    assert len(due_result_races([(day+"|26|1", gate_rows)], stale,
                              after + timedelta(days=1))[0]) == 1
    # At JST 00:10 on Nov 24, all seven Nov 23 midnight races are due,
    # while Nov 24 racecards must remain withheld without source-bound time.
    night_entries = []
    for rnum in range(1, 8):
        for row in records:
            copy_row = list(row)
            copy_row[0], copy_row[1], copy_row[2], copy_row[3] = (
                "2026-11-23", "61", "玉野", str(rnum))
            night_entries.append(copy_row)
    next_day = []
    for row in records:
        copy_row = list(row)
        copy_row[0], copy_row[1], copy_row[2], copy_row[3] = (
            "2026-11-24", "61", "玉野", "1")
        next_day.append(copy_row)
    all_night = eligible_races(night_entries + next_day, [],
                               date(2026, 11, 23), date(2026, 11, 24))
    assert len(all_night) == 8
    midnight = datetime(2026, 11, 24, 0, 10, tzinfo=JST)
    ready, withheld = due_result_races(
        all_night, {"schema": "ki-daily-start-times-v1", "races": {}},
        midnight)
    assert [k for k, _ in ready] == [
        f"2026-11-23|61|{rnum}" for rnum in range(1, 8)]
    assert withheld == ["2026-11-24|61|1"]
    assert len(select_rotating_races(ready, 12, midnight)) == 7
    gated = process(gate_rows, [], start, start, collect_fn=lambda *a: actual,
                    apply_fn=pretend_apply, start_times=cache, now=before)
    assert gated["notYetDueCount"] == 1 and gated["eligibleExamined"] == 0
    assert gated["savedCount"] == 0
    assert summary["results"][0]["status"] == "DRY_RUN_TWO_SOURCES_MATCH" and calls == [True]
    assert (summary["eligibleTotal"], summary["eligibleExamined"], summary["eligibleDeferred"], summary["savedCount"]) == (1, 1, 0, 0)
    assert summary["results"][0]["secondSourceId"] == "chariloto-day-results"
    assert summary["results"][0]["alternateSourceUsed"] is False
    alternate = {"observations": [left, dict(right, sourceId="lotoplace-day-results",
                                           sourceUrl="https://www.lotoplace.jp/keirin/results/26/2026-11-23/")],
                 "comparison": compare({"observations": [left, dict(right, sourceId="lotoplace-day-results",
                                           sourceUrl="https://www.lotoplace.jp/keirin/results/26/2026-11-23/")]})}
    alt_report = process(records, [], start, start, collect_fn=lambda *a: alternate,
                         apply_fn=pretend_apply)
    assert alt_report["results"][0]["alternateSourceUsed"] is True
    calls.pop()  # restore the original one-write expectation for the following identity test
    broken = [list(x) for x in records]
    broken[0][6] = "別人"
    summary = process(broken, [], start, start, collect_fn=lambda *a: actual,
                      apply_fn=pretend_apply)
    assert summary["results"][0]["status"] == "SOURCE_OR_IDENTITY_REVIEW_NO_WRITE"
    assert calls == [True]
    assert summary["results"][0]["failurePhase"] == "COLLECT_COMPARE"
    assert summary["results"][0]["reasonCode"] == "ENTRY_RIDER_IDENTITY_MISMATCH"
    assert summary["results"][0]["reviewRoute"] == "RIDER_OR_CLASS_EVIDENCE_REVIEW"
    from collect_historical_pair import SourceStageError
    def fail_primary(*args):
        try:
            raise ValueError("Robots rules prohibit this page")
        except ValueError as exc:
            raise SourceStageError("PRIMARY_NETKEIRIN") from exc
    source_hold = process(records, [], start, start, collect_fn=fail_primary,
                          apply_fn=pretend_apply)
    assert source_hold["results"][0]["sourceStage"] == "PRIMARY_NETKEIRIN"
    assert source_hold["results"][0]["reasonCode"] == "SOURCE_ROBOTS_DISALLOWED"
    def fail_secondary(*args):
        try:
            raise ValueError("Exactly one complete target-race result table required")
        except ValueError as exc:
            raise SourceStageError("SECONDARY_BOTH_UNAVAILABLE") from exc
    source_hold = process(records, [], start, start, collect_fn=fail_secondary,
                          apply_fn=pretend_apply)
    assert source_hold["results"][0]["sourceStage"] == "SECONDARY_BOTH_UNAVAILABLE"
    assert source_hold["results"][0]["reasonCode"] == "SOURCE_INCOMPLETE_OR_AMBIGUOUS_TABLE"
    assert classify_result_hold(ValueError("Rider class conflicts with requested race class"), "COLLECT_COMPARE") == "SOURCE_RIDER_CLASS_MISMATCH"
    assert classify_result_hold(ValueError("Unexpected Sheet response"), "SHEETS_DRY_RUN") == "SHEETS_OTHER_ERROR"
    assert eligible_races(records, [[""] * 14 + ["2026-11-23|26|1"]], start, start) == []
    partial_rows = [list(x) + [""] * (15 - len(x)) for x in records[:3]]
    for row in partial_rows:
        row[14] = "2026-11-23|26|1"
    flags = partial_existing_results(records, partial_rows, start, start)
    assert len(flags) == 1 and flags[0]["expectedCars"] == 7
    assert flags[0]["storedRows"] == 3
    assert flags[0]["missingCarNumbers"] == ["4", "5", "6", "7"]
    assert flags[0]["duplicateCarNumbers"] == []
    assert flags[0]["unexpectedCarNumbers"] == []
    assert partial_existing_results(records, partial_rows + partial_rows, start, start)[0]["duplicateCarNumbers"] == ["1", "2", "3"]
    assert partial_existing_results(records, partial_rows + partial_rows, start, start)[0]["storedRows"] == 6
    full_rows = [list(x) + [""] * (15 - len(x)) for x in records]
    for row in full_rows:
        row[14] = "2026-11-23|26|1"
    assert partial_existing_results(records, full_rows, start, start) == []
    # Partial result completion writes only proven missing rider rows.
    preexisting = [list(row) + [""] * (15 - len(row)) for row in records[:3]]
    for i, row in enumerate(preexisting):
        row[9] = str(i + 1)
        row[10] = "差" if i == 0 else ""
        row[14] = day + "|26|1"
    complete_candidate = candidate(day+"|26|1", records, collect_fn=lambda *a: actual)
    only_missing = safe_missing_result_payload(complete_candidate, preexisting, records)
    assert [x["number"] for x in only_missing["results"]] == [4, 5, 6, 7]
    partial_calls = []
    def partial_apply(data, dry_run=True):
        partial_calls.append((dry_run, len(data["results"])))
        return {"summary": {"entries": {"new": 0, "changed": 0},
                            "results": {"new": len(data["results"]), "changed": 0}}}
    repaired = process(records, preexisting, start, start, collect_fn=lambda *a: actual,
                       apply_fn=partial_apply)
    assert repaired["eligibleTotal"] == 1 and repaired["eligibleExamined"] == 1
    assert repaired["results"][0]["partialCompleted"] is True
    assert repaired["results"][0]["cars"] == 4 and partial_calls == [(True, 4)]
    preexisting[1][9] = "7"  # already-recorded finish conflicts with source
    partial_calls.clear()
    held = process(records, preexisting, start, start, collect_fn=lambda *a: actual,
                   apply_fn=partial_apply)
    assert held["savedCount"] == 0 and partial_calls == []
    assert held["results"][0]["status"] == "SOURCE_OR_IDENTITY_REVIEW_NO_WRITE"
    # Complete car-number coverage alone must not conceal wrong rider identity.
    wrong_rider = [list(row) for row in full_rows]
    wrong_rider[2][6] = "別人"
    mismatch = partial_existing_results(records, wrong_rider, start, start)
    assert len(mismatch) == 1 and mismatch[0]["identityMismatchCars"] == ["3"]
    wrong_track = [list(row) for row in full_rows]
    wrong_track[0][2] = "別競輪場"
    assert partial_existing_results(records, wrong_track, start, start)[0]["identityMismatchCars"] == ["1"]
    # Repeated source failures at the start of the backlog must not starve later races.
    rotation = [(f"race-{i}", []) for i in range(13)]
    day0 = datetime(2026, 11, 23, 7, 10, tzinfo=JST)
    batches = [select_rotating_races(rotation, 4, day0.replace(hour=h))
               for h in (0, 7, 12, 17, 22)]
    assert all(1 <= len(batch) <= 4 for batch in batches)
    assert len({k for batch in batches for k, _ in batch}) == 13
    overnight = day0.replace(hour=0)
    # Five distinct slot indices are observable only with >=5 candidate blocks.
    five_blocks = [(f"race-{i}", []) for i in range(20)]
    assert len({tuple(k for k, _ in select_rotating_races(five_blocks, 4,
               overnight.replace(hour=h))) for h in (0, 7, 12, 17, 22)}) == 5
    # The production limit is twelve races; verify all five JST windows
    # eventually cover every candidate even when the backlog spans days.
    for count in (12, 13, 48, 49, 80):
        candidates = [(f"race-{i}", []) for i in range(count)]
        covered = set()
        for offset in range(6):
            for hour in (0, 7, 12, 17, 22):
                moment = (day0 + timedelta(days=offset)).replace(hour=hour)
                covered.update(key for key, _ in select_rotating_races(candidates, 12, moment))
        assert covered == {key for key, _ in candidates}, count
    assert select_rotating_races([], 4) == []
    exhausted = process(records, [], start, start, collect_fn=lambda *a: actual,
                        apply_fn=pretend_apply, max_seconds=60,
                        monotonic_fn=iter((0, 61)).__next__)
    assert exhausted["eligibleExamined"] == 0 and exhausted["eligibleDeferred"] == 1
    assert exhausted["timeBudgetExceeded"] and exhausted["savedCount"] == 0
    # A non-tautological regression for the midnight/07:10 rotation boundary.
    assert [k for k, _ in select_rotating_races(rotation, 4,
           day0.replace(hour=0))] == ["race-12"]
    assert [k for k, _ in select_rotating_races(rotation, 4,
           day0)] == ["race-0", "race-1", "race-2", "race-3"]
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
                     write=args.apply, max_seconds=args.max_seconds,
                     start_times=load_start_time_cache())
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if "--self-test" in sys.argv:
            import traceback
            traceback.print_exc()
        else:
            print("DAILY_RESULT_ABORT: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
