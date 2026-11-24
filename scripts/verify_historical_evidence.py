#!/usr/bin/env python3
"""Recheck unpublished content-PASS rows against live original HTML (read-only).

No Google writes or formal feed promotion. Uses the existing robots-gated
Chariloto parser and the stored V99 slice, then rereads that exact V99 range.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import requests

from collect_lotoplace_result import EXCEPTION_LABELS, fetch, parse_result, validate_url
from compare_race_results import (
    canonical_method, normalized_name, normalized_prefecture,
)

SHEET_ID = "1gCe5q5STYH0T8XKqxJbVawB0Cl8TPsCISFJiRUdA02M"
SOURCE_TAB = "KI｜レース結果手動照合"
V99_TAB = "V99選手結果蓄積"


def sheet_ranges(creds, ranges):
    response = requests.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values:batchGet",
        params=[("ranges", name) for name in ranges],
        headers={"Authorization": "Bearer " + creds.token}, timeout=45,
    )
    response.raise_for_status()
    result = response.json().get("valueRanges", [])
    if len(result) != len(ranges):
        raise ValueError("Google Sheets returned incomplete ranges")
    return [part.get("values", []) for part in result]


def class_group(values):
    groups = {
        "A3": "A3", "A1": "A1A2", "A2": "A1A2",
        "S1": "S", "S2": "S", "SS": "S",
        "L1": "L1", "L2": "L1",
    }
    selected = {groups.get(str(v)) for v in values}
    if len(selected) != 1 or None in selected:
        raise ValueError("Unsupported mixed race grades")
    return selected.pop()


def normalized_finish(value):
    value = str(value or "").strip()
    if value.isdecimal():
        return str(int(value))
    return EXCEPTION_LABELS.get(value, value)


def verify_row(row, reread, cache):
    date, code, race_num = row[3].split("|")
    race = int(race_num)
    if not re.fullmatch(r"20\d\d-\d\d-\d\d", date) or not code.isdigit() or not 1 <= race <= 12:
        raise ValueError("Invalid race key")
    url, track = row[10], row[5]
    proof, observation = json.loads(row[11]), json.loads(row[12])
    if (proof.get("kind") not in ("web_indexed_full_result_text", "v99_complete_source_candidate")
            or proof.get("sourceUrl") != url
            or observation.get("raceKey") != row[3]
            or observation.get("sourceUrl") != url
            or observation.get("formalPublished") is not False
            or row[0] == ""):
        raise ValueError("Conflicting evidence metadata or published state")
    validate_url(url, date, code)
    if urlsplit(url).netloc != "www.chariloto.com":
        raise ValueError("This validator handles only live Chariloto")
    count = int(row[13].split("/")[0])
    if count not in (7, 9) or row[13] != f"{count}/{count}":
        raise ValueError("Incomplete original field")
    stored = json.loads(row[9])
    # Sheets omits empty cells in API ranges, while evidence JSON stores them
    # as null. Compare the same 23 original columns after empty normalization.
    def canonical_v99(values):
        return [[str(row[i] if i < len(row) and row[i] is not None else "")
                 for i in range(23)] for row in values]
    if len(stored) != count or len(reread) != count or canonical_v99(reread) != canonical_v99(stored):
        raise ValueError("V99 original rows changed since evidence saving")
    grades = class_group(x[12] for x in stored)
    if any(x[0] != date or str(x[2]).zfill(2) != code or int(x[4]) != race
           or x[1] != track for x in stored):
        raise ValueError("Race identity differs in V99")
    if url not in cache:
        cache[url] = fetch(url)
    observed = parse_result(cache[url], date, code, track, race, grades, count, url)
    riders = {int(item["number"]): item for item in observed["results"]}
    if len(riders) != count or set(riders) != set(range(1, count + 1)):
        raise ValueError("Missing or duplicate source car")
    for original in stored:
        car = int(original[7])
        source = riders[car]
        actual = (
            normalized_finish(source["finish"]),
            normalized_name(source["name"]),
            normalized_prefecture(source["prefecture"]),
            str(source["period"]).removesuffix("期"),
            canonical_method(source["method"]),
            str(source["exception"] or ""),
        )
        expected = (
            normalized_finish(original[6]),
            normalized_name(original[8]),
            normalized_prefecture(original[10]),
            str(original[11]).removesuffix("期"),
            canonical_method(original[15]),
            str(original[17] or ""),
        )
        # Non-numeric abbreviated statuses normalize only where they represent
        # non-finishing; a numeric placing plus 『落』 remains its own condition.
        if not str(original[6]).isdecimal():
            expected = expected[:-1] + (EXCEPTION_LABELS.get(expected[-1], expected[-1]),)
        if actual != expected or str(original[12]) not in ("A3", "A1", "A2", "S1", "S2", "SS", "L1", "L2"):
            raise ValueError(f"Car {car}: original V99 identity/result differs")
    return count


def fresh_candidates(rows, excluded, limit=10, offset=0):
    """Select complete, contiguous V99 races; never treat selection as PASS."""
    if not 1 <= limit <= 10 or offset < 0:
        raise ValueError("Invalid candidate window")
    grouped = {}
    for index, raw in enumerate(rows, start=2):
        if len(raw) < 8:
            continue
        row = [str(v or "") for v in raw] + [""] * max(0, 23 - len(raw))
        day, track, code, number = row[0], row[1], row[2], row[4]
        if not re.fullmatch(r"20\\d{2}-\\d{2}-\\d{2}", day) or not code.isdecimal() or not number.isdecimal():
            continue
        if not 1 <= int(code) <= 99 or not 1 <= int(number) <= 12 or not track:
            continue
        key = f"{day}|{int(code):02d}|{int(number)}"
        if key not in excluded:
            grouped.setdefault(key, []).append((index, row))
    candidates = []
    for key, group in grouped.items():
        indices = [i for i, _ in group]
        original = [row for _, row in group]
        count = len(original)
        if count not in (7, 9) or indices != list(range(indices[0], indices[0] + count)):
            continue
        try:
            if sorted(int(x[7]) for x in original) != list(range(1, count + 1)):
                continue
            if any(not x[8] or not x[10] or not x[11].removesuffix("期").isdigit() for x in original):
                continue
            grade = class_group(x[12] for x in original)
            if len({x[1] for x in original}) != 1:
                continue
        except (ValueError, TypeError):
            continue
        day, code, race = key.split("|")
        url = f"https://www.chariloto.com/keirin/results/{int(code)}/{day}"
        # A transient candidate is not a Google evidence record.
        proof = {"kind": "v99_complete_source_candidate", "sourceUrl": url}
        observation = {"raceKey": key, "sourceUrl": url, "formalPublished": False}
        row = [""] * 21
        row[0] = "UNSAVED-V99-" + key
        row[3], row[5] = key, original[0][1]
        row[8] = f"{V99_TAB}!A{indices[0]}:W{indices[-1]}"
        row[9], row[10] = json.dumps(original, ensure_ascii=False), url
        row[11], row[12] = json.dumps(proof), json.dumps(observation)
        row[13] = f"{count}/{count}"
        candidates.append((grade not in ("A3", "A1A2") or count != 7, key, row))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in candidates[offset:offset + limit]]


def self_test():
    def race(number, start=1):
        rows = []
        for car in range(start, 8):
            row = [""] * 23
            row[0], row[1], row[2], row[4] = "2026-10-01", "久留米", "83", str(number)
            row[6], row[7], row[8], row[10], row[11], row[12] = str(car), str(car), f"選手{car}", "福岡", "99", "A3"
            rows.append(row)
        return rows
    rows = race(1) + race(2) + race(3, 2) + race(4)
    found = fresh_candidates(rows, {"2026-10-01|83|1"})
    assert [r[3] for r in found] == ["2026-10-01|83|2", "2026-10-01|83|4"]
    assert found[0][8] == f"{V99_TAB}!A9:W15"
    assert fresh_candidates(rows, set(), limit=1, offset=1)[0][3] == "2026-10-01|83|2"
    assert not fresh_candidates(race(1) + race(1), set())
    assert all(r[0].startswith("UNSAVED-V99-") for r in found)
    print("SELF_TEST_OK: V99 fallback excludes published, incomplete and duplicate races")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.offset < 0:
        parser.error("offset must be nonnegative")
    import google.auth.transport.requests
    from google.oauth2 import service_account
    secret = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not secret:
        raise RuntimeError("Missing read-only Sheets credential")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(secret), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    creds.refresh(google.auth.transport.requests.Request())
    source = sheet_ranges(creds, [f"'{SOURCE_TAB}'!A1:U2000"])[0][1:]
    official = json.loads(Path("verified-results-feed-v1.json").read_text(encoding="utf-8"))
    published = {x["key"] for x in official["races"]}
    pending = []
    for row in source:
        if len(row) < 19 or (row[16], row[17]) not in (
            ("PASS", "PASS_FALLBACK_CONTENT_ONLY"), ("PENDING", "WAIT_LIVE_HTML")
        ):
            continue
        if row[3] in published:
            continue
        try:
            proof = json.loads(row[11])
            if proof.get("kind") not in ("web_indexed_full_result_text", "v99_complete_source_candidate"):
                continue
            if not re.fullmatch(r"V99選手結果蓄積!A\d+:W\d+", row[8]):
                continue
            pending.append(row)
        except (ValueError, TypeError):
            continue
    pending = pending[:10]
    if len(pending) < 10:
        original_rows = sheet_ranges(creds, [f"'{V99_TAB}'!A2:W"])[0]
        excluded = published | {row[3] for row in source if len(row) > 3}
        pending.extend(fresh_candidates(original_rows, excluded, limit=10-len(pending), offset=args.offset))
    if not pending:
        print("HISTORICAL_PROOF_NO_ELIGIBLE_CANDIDATES")
        return
    ranges = ["'" + row[8].replace("!", "'!") for row in pending]
    stored_ranges = sheet_ranges(creds, ranges)
    cache = {}
    passed = 0
    for row, original in zip(pending, stored_ranges):
        try:
            count = verify_row(row, original, cache)
            passed += 1
            run_url = os.environ.get("GITHUB_RUN_URL", "")
            print("HISTORICAL_NEW_CANDIDATE_LIVE_HTML_OK" if row[0].startswith("UNSAVED-V99-") else "HISTORICAL_PROOF_LIVE_HTML_OK", row[3], "cars", count,
                  "evidenceRef", row[0], "source", row[10], "run", run_url)
        except (ValueError, requests.RequestException, KeyError, IndexError) as exc:
            print("HISTORICAL_PROOF_HOLD", row[3], type(exc).__name__, str(exc)[:150])
    print("HISTORICAL_PROOF_SUMMARY", passed, "/", len(pending),
          "read-only; no formal publication or Google writes")
    if passed != len(pending):
        raise SystemExit(2)  # Incomplete proof must not report a successful workflow.


if __name__ == "__main__":
    main()
