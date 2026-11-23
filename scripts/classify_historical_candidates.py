#!/usr/bin/env python3
"""Classify collected historical candidates vs a scoped V99 sheet snapshot.

Read-only; never promotes PASS or writes Sheets. Snapshot is JSON:
{"schema":"ki-v99-snapshot-v1","coverage":["2026-09-10|27|2"],
 "rows":[[V99's 23 column header], [all matching rows], ...]}
coverage must list ONLY race keys confirmed exhaustively searched in V99.
Without explicit coverage, status is LEDGER_COVERAGE_UNCONFIRMED, not "new".
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from compare_race_results import compare, canonical_method, normalized_name

COLUMNS = {
    "date": 0, "track": 1, "code": 2, "race": 4, "finish": 6,
    "number": 7, "name": 8, "prefecture": 10, "period": 11,
    "class": 12, "method": 15, "exception": 17,
}
HEADER = ["開催日", "競輪場", "場コード", "グレード", "R", "レース級",
          "着順原文", "車番", "選手名", "年齢", "府県", "期別",
          "選手級班", "着差", "上り", "決まり手", "S/B", "個人状況"]
STATUSES = {"欠車", "取消", "失格", "落車棄権", "途中棄権", "棄権"}
SHORT = {"失": "失格", "欠": "欠車", "取": "取消", "落": "落車棄権",
         "棄": "棄権", "途": "途中棄権"}
FIELDS = ("name", "prefecture", "period", "finish", "method", "exception")


def norm(v):
    return unicodedata.normalize("NFKC", str(v or "")).strip()


def canonical_finish(v):
    v = norm(v)
    if v in SHORT:
        return SHORT[v]
    if v.isdecimal():
        return str(int(v))
    return v


def row_key(row):
    try:
        day, code, r = norm(row[0]), norm(row[2]), norm(row[4])
        if not re.fullmatch(r"20\d\d-\d\d-\d\d", day):
            raise ValueError("Invalid sheet date")
        if not code.isdecimal() or not r.isdecimal() or not 1 <= int(code) <= 99 or not 1 <= int(r) <= 12:
            raise ValueError("Invalid sheet race key")
        return f"{day}|{int(code):02d}|{int(r)}"
    except IndexError as e:
        raise ValueError("Sheet row is too short") from e


def ledger_records(snapshot, racekey):
    if snapshot.get("schema") != "ki-v99-snapshot-v1":
        raise ValueError("Unrecognized V99 snapshot")
    coverage = snapshot.get("coverage")
    if not isinstance(coverage, list) or any(not isinstance(k, str) for k in coverage):
        raise ValueError("Missing snapshot coverage list")
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or not rows or rows[0][:len(HEADER)] != HEADER:
        raise ValueError("V99 header mismatch")
    if racekey not in coverage:
        return None
    found = {}
    for raw in rows[1:]:
        if not isinstance(raw, list):
            raise ValueError("Non-array V99 sheet row")
        if not raw or not norm(raw[0]):
            continue
        key = row_key(raw)
        if key != racekey:
            continue
        raw = list(raw) + [""] * max(0, 18 - len(raw))
        number = norm(raw[COLUMNS["number"]])
        if not number.isdecimal() or not 1 <= int(number) <= 9:
            raise ValueError("Invalid V99 rider car number")
        car = int(number)
        if car in found:
            raise ValueError("Duplicate V99 car number")
        finish = canonical_finish(raw[COLUMNS["finish"]])
        exception = canonical_finish(raw[COLUMNS["exception"]])
        if finish in STATUSES and not exception:
            exception = finish
        found[car] = {
            "name": normalized_name(raw[COLUMNS["name"]]),
            "prefecture": norm(raw[COLUMNS["prefecture"]]),
            "period": re.sub(r"期$", "", norm(raw[COLUMNS["period"]])),
            "finish": finish,
            "method": canonical_method(raw[COLUMNS["method"]]),
            "exception": exception,
            "grade": norm(raw[COLUMNS["class"]]),
            "track": norm(raw[COLUMNS["track"]]),
        }
    return found


def classify(candidate, snapshot):
    observations = candidate.get("observations")
    if not isinstance(observations, list) or len(observations) != 2:
        raise ValueError("Candidate must contain two observations")
    recomputed = compare({"observations": observations})
    if candidate.get("comparison") != recomputed or recomputed["formalPass"] is not False:
        raise ValueError("Candidate comparison is stale or tampered")
    key = recomputed["raceKey"]
    base = {"raceKey": key, "formalPass": False, "carCount": recomputed["carCount"]}
    if recomputed["disagreements"]:
        return {**base, "classification": "SOURCE_CONFLICT_REVIEW_REQUIRED",
                "details": ["Two sources disagree; do not classify against ledger as matched"]}
    existing = ledger_records(snapshot, key)
    if existing is None:
        return {**base, "classification": "LEDGER_COVERAGE_UNCONFIRMED", "details": []}
    if not existing:
        return {**base, "classification": "NOT_IN_SCOPED_LEDGER", "details": []}
    expected = recomputed["carCount"]
    if len(existing) != expected or set(existing) != set(range(1, expected + 1)):
        return {**base, "classification": "PARTIAL_OR_INVALID_LEDGER_RACE",
                "ledgerCars": len(existing), "details": []}
    observed = {}
    for row in observations[0]["results"]:
        observed[int(row["number"])] = row
    problems = []
    grade = norm(observations[0]["race"]["className"])
    track = norm(observations[0]["race"]["track"])
    for car in sorted(existing):
        record = existing[car]
        if record["track"] != track:
            problems.append({"car": car, "field": "track"})
        # V99 grade is per-rider (A3/A2/S1...), A1A2/S can contain subgrades.
        if grade in ("A3", "A1", "A2", "S1", "S2", "L1") and record["grade"] and record["grade"] != grade:
            problems.append({"car": car, "field": "grade"})
        entry = observed[car]
        comparisons = {
            "name": normalized_name(entry["name"]),
            "prefecture": norm(entry["prefecture"]),
            "period": norm(entry["period"]).removesuffix("期"),
            "finish": canonical_finish(entry["finish"]),
            "method": canonical_method(entry["method"]),
            "exception": canonical_finish(entry["exception"]),
        }
        for field in FIELDS:
            # Empty method/exception on either side means unconfirmed, not equality.
            v99 = record[field]
            live = comparisons[field]
            if field in ("method", "exception") and (not v99 or not live):
                if v99 != live:
                    problems.append({"car": car, "field": field, "kind": "MISSING_OR_DIFFERENT"})
                continue
            if v99 != live:
                problems.append({"car": car, "field": field})
    return {**base, "classification": "REGISTERED_CONTENT_MATCH" if not problems
            else "LEDGER_CONFLICT_OR_MISSING_FIELDS", "details": problems}


def self_test():
    race = {"date": "2026-09-10", "trackCode": "27", "track": "京王閣",
            "race": 2, "className": "A3", "expectedCars": 7}
    riders = [{"number": i, "name": "選手" + str(i), "prefecture": "京都",
               "period": "93", "finish": str(i), "method": "差" if i == 1 else "",
               "exception": ""} for i in range(1, 8)]
    a = {"sourceUrl": "https://one.example/r", "sourceId": "one",
         "race": dict(race), "results": [dict(x) for x in riders]}
    b = {"sourceUrl": "https://two.example/r", "sourceId": "two",
         "race": dict(race), "results": [dict(x) for x in riders]}
    candidate = {"observations": [a, b], "comparison": compare({"observations": [a, b]})}
    rows = [HEADER + ["正式選手ID", "照合状態", "出典URL", "取得日時"]]
    for x in riders:
        row = [""] * 23
        row[0], row[1], row[2], row[4] = race["date"], race["track"], race["trackCode"], "2"
        row[6], row[7], row[8], row[10], row[11], row[12] = x["finish"], str(x["number"]), x["name"], x["prefecture"], x["period"], "A3"
        row[15] = x["method"]
        rows.append(row)
    snapshot = {"schema": "ki-v99-snapshot-v1", "coverage": ["2026-09-10|27|2"], "rows": rows}
    assert classify(candidate, snapshot)["classification"] == "REGISTERED_CONTENT_MATCH"
    assert classify(candidate, {**snapshot, "coverage": []})["classification"] == "LEDGER_COVERAGE_UNCONFIRMED"
    assert classify(candidate, {**snapshot, "rows": [rows[0]]})["classification"] == "NOT_IN_SCOPED_LEDGER"
    assert classify(candidate, {**snapshot, "rows": rows[:-1]})["classification"] == "PARTIAL_OR_INVALID_LEDGER_RACE"
    rows[1][6] = "2"
    assert classify(candidate, snapshot)["classification"] == "LEDGER_CONFLICT_OR_MISSING_FIELDS"
    print("SELF_TEST_OK: V99 coverage, full match, missing, partial and conflicting rows")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    result = classify(candidate, snapshot)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
