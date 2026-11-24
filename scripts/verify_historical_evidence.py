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
    validate_url(url, date, code)
    if urlsplit(url).netloc != "www.chariloto.com":
        raise ValueError("This validator handles only live Chariloto")
    count = int(row[13].split("/")[0])
    if count not in (7, 9) or row[13] != f"{count}/{count}":
        raise ValueError("Incomplete original field")
    stored = json.loads(row[9])
    if len(stored) != count or reread != stored:
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


def main():
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
        if len(row) < 19 or row[16] != "PASS" or row[17] != "PASS_FALLBACK_CONTENT_ONLY":
            continue
        if row[3] in published:
            continue
        try:
            proof = json.loads(row[11])
            if proof.get("kind") != "web_indexed_full_result_text":
                continue
            if not re.fullmatch(r"V99選手結果蓄積!A\d+:W\d+", row[8]):
                continue
            pending.append(row)
        except (ValueError, TypeError):
            continue
    pending = pending[:6]
    if not pending:
        print("HISTORICAL_PROOF_NO_PENDING_CONTENT_PASS")
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
            print("HISTORICAL_PROOF_LIVE_HTML_OK", row[3], "cars", count,
                  "evidenceRef", row[0], "source", row[10], "run", run_url)
        except (ValueError, requests.RequestException, KeyError, IndexError) as exc:
            print("HISTORICAL_PROOF_HOLD", row[3], type(exc).__name__, str(exc)[:150])
    print("HISTORICAL_PROOF_SUMMARY", passed, "/", len(pending),
          "read-only; no formal publication or Google writes")


if __name__ == "__main__":
    main()
