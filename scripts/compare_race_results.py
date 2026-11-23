#!/usr/bin/env python3
"""Shared daily/historical result comparison. Candidate-only; never grants formal PASS.

Input is a JSON object with two separately collected source observations:
  {"observations":[{"sourceUrl":"https://...","sourceId":"...",
    "race":{"date":"2026-11-23","trackCode":"26","track":"西武園",
            "race":1,"className":"A3","expectedCars":7},
    "results":[{"number":1,"name":"...","prefecture":"...","period":"93",
                "finish":"1","method":"差し","exception":""}, ...]}, ...]}
All 7/9 cars must be present, including absences/disqualifications, before comparison.
PASS requires independent publication provenance and is outside this module.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

EXCEPTIONS = {"欠車", "取消", "失格", "落車棄権", "途中棄権", "棄権"}
METADATA = ("date", "trackCode", "track", "race", "className", "expectedCars")
RIDER_FIELDS = ("name", "prefecture", "period", "finish", "method", "exception")


def clean(value):
    return unicodedata.normalize("NFKC", str(value if value is not None else "")).strip()


def normalized_name(value):
    # Spaces between Japanese surname and given name are presentation differences.
    return re.sub(r"\s+", "", clean(value))


def require_source(observation):
    url = clean(observation.get("sourceUrl"))
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Observation must cite an HTTPS source URL")
    return url, parsed.hostname.lower()


def normalized_race(observation):
    race = observation.get("race")
    if not isinstance(race, dict):
        raise ValueError("Missing race metadata")
    values = {key: clean(race.get(key)) for key in METADATA}
    try:
        day = date.fromisoformat(values["date"])
        if day.strftime("%Y-%m-%d") != values["date"]:
            raise ValueError("Noncanonical race date")
        track_code = values["trackCode"]
        if not track_code.isdigit() or not 1 <= int(track_code) <= 99:
            raise ValueError("Invalid track code")
        values["trackCode"] = track_code.zfill(2)
        n = int(values["race"])
        if not 1 <= n <= 12 or str(n) != values["race"]:
            raise ValueError("Invalid race number")
        values["race"] = n
        cars = int(values["expectedCars"])
        if cars not in (7, 9):
            raise ValueError("Unsupported field size")
        values["expectedCars"] = cars
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid race metadata: " + str(exc)) from exc
    if not values["track"] or not values["className"]:
        raise ValueError("Track and class cannot be blank")
    return values


def normalized_results(observation, expected):
    rows = observation.get("results")
    if not isinstance(rows, list) or len(rows) != expected:
        raise ValueError("Expected full results for all scheduled cars")
    normalized = {}
    finishes = []
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError("Non-object result row")
        raw_car = clean(r.get("number"))
        if not raw_car.isdigit() or not 1 <= int(raw_car) <= expected:
            raise ValueError("Invalid car number")
        car = int(raw_car)
        if car in normalized:
            raise ValueError("Duplicate car in result observation")
        attrs = {field: clean(r.get(field)) for field in RIDER_FIELDS}
        attrs["name"] = normalized_name(attrs["name"])
        attrs["period"] = re.sub(r"期$", "", attrs["period"])
        if not attrs["name"] or not attrs["prefecture"] or not attrs["period"].isdigit():
            raise ValueError("Unidentified rider in result observation")
        finish, ex = attrs["finish"], attrs["exception"]
        if finish in EXCEPTIONS and not ex:
            ex = finish
        if ex and ex not in EXCEPTIONS:
            raise ValueError("Unknown result exception")
        if finish.isdigit():
            if not 1 <= int(finish) <= expected or ex:
                raise ValueError("Numeric finish conflicts with exception")
            finishes.append(int(finish))
            attrs["finish"] = str(int(finish))
        elif finish in EXCEPTIONS:
            if ex != finish:
                raise ValueError("Conflicting exception and finish")
        else:
            raise ValueError("Invalid result finish/state")
        attrs["exception"] = ex
        normalized[car] = attrs
    if sorted(normalized) != list(range(1, expected + 1)):
        raise ValueError("Incomplete car numbers in result observation")
    if len(finishes) != len(set(finishes)):
        raise ValueError("Duplicate numeric finishing position")
    return normalized


def compare(payload):
    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(observations, list) or len(observations) != 2:
        raise ValueError("Exactly two source observations required")
    parsed = []
    for item in observations:
        if not isinstance(item, dict):
            raise ValueError("Observation must be object")
        url, host = require_source(item)
        race = normalized_race(item)
        rows = normalized_results(item, race["expectedCars"])
        source_id = clean(item.get("sourceId"))
        if not source_id:
            raise ValueError("SourceId required to track provenance")
        parsed.append((url, host, source_id, race, rows))
    url_a, host_a, id_a, race_a, rows_a = parsed[0]
    url_b, host_b, id_b, race_b, rows_b = parsed[1]
    if url_a == url_b or host_a == host_b or id_a == id_b:
        raise ValueError("Two distinct publication identities required")
    if race_a != race_b:
        raise ValueError("Race metadata mismatch; no comparison status")
    disagreements = []
    for number in sorted(rows_a):
        a, b = rows_a[number], rows_b[number]
        for field in RIDER_FIELDS:
            if a[field] != b[field]:
                disagreements.append({"number": number, "field": field,
                                      "left": a[field], "right": b[field]})
    return {
        "schema": "ki-result-comparison-v1",
        "raceKey": f'{race_a["date"]}|{race_a["trackCode"]}|{race_a["race"]}',
        "carCount": race_a["expectedCars"],
        "status": "SOURCE_CONTENT_MATCH_INDEPENDENCE_PENDING" if not disagreements
                  else "SOURCE_CONFLICT_REVIEW_REQUIRED",
        "sourceDomains": sorted([host_a, host_b]),
        "disagreements": disagreements,
        "formalPass": False,
        "note": "Content comparison only. Check upstream independence, raw evidence, "
                "scheduled field/absences, identity, and existing formal publication rules."
    }


def self_test():
    race = dict(date="2026-11-23", trackCode="26", track="西武園",
                race=1, className="A3", expectedCars=7)
    rows = [dict(number=i, name=f"テスト 選手{i}", prefecture="京都",
                 period="93", finish=str(i), method="差し" if i == 1 else "",
                 exception="") for i in range(1, 8)]
    def observation(url, sid):
        return dict(sourceUrl=url, sourceId=sid, race=dict(race),
                    results=[dict(x) for x in rows])
    a, b = observation("https://source-a.example/r", "a"), observation(
        "https://source-b.example/r", "b")
    assert compare({"observations": [a, b]})["status"] == "SOURCE_CONTENT_MATCH_INDEPENDENCE_PENDING"
    b["results"][0]["finish"] = "2"
    b["results"][1]["finish"] = "1"
    assert compare({"observations": [a, b]})["status"] == "SOURCE_CONFLICT_REVIEW_REQUIRED"
    b["results"][0]["finish"] = "1"
    b["results"][1]["finish"] = "2"
    b["results"].pop()
    try:
        compare({"observations": [a, b]})
    except ValueError:
        pass
    else:
        raise AssertionError("Incomplete scheduled field accepted")
    b["results"].append(dict(rows[-1]))
    b["sourceUrl"] = "https://source-a.example/another"
    try:
        compare({"observations": [a, b]})
    except ValueError:
        pass
    else:
        raise AssertionError("Same-domain duplication accepted")
    print("SELF_TEST_OK: full-field match/conflict, missing car and same-domain guards")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input")
    p.add_argument("--out")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.input:
        p.error("--input required")
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = compare(payload)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("NO_PUBLISH: " + str(exc), file=sys.stderr)
        sys.exit(1)
