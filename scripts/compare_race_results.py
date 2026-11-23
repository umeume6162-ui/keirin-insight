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
    value = re.sub(r"\s+", "", clean(value))
    # Evidence-scoped rider aliases. Never apply generic kanji substitutions.
    return {"国井裕樹": "國井裕樹"}.get(value, value)


def normalized_prefecture(value):
    value = clean(value)
    # Published abbreviations already verified in the pre-race identity matcher.
    return {"神奈": "神奈川", "北海": "北海道",
            "鹿児": "鹿児島"}.get(value, value)


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


def canonical_method(value):
    """Normalize only established keirin decision-word equivalents."""
    raw = clean(value)
    return {
        "差し": "差", "差": "差",
        "捲り": "捲", "捲くり": "捲", "まくり": "捲", "捲": "捲",
        "逃げ": "逃", "逃": "逃",
        "マーク": "ク", "ク": "ク",
    }.get(raw, raw)


def normalized_results(observation, expected):
    rows = observation.get("results")
    if not isinstance(rows, list) or len(rows) != expected:
        raise ValueError("Expected full results for all scheduled cars")
    normalized = {}
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
        attrs["prefecture"] = normalized_prefecture(attrs["prefecture"])
        attrs["period"] = re.sub(r"期$", "", attrs["period"])
        attrs["method"] = canonical_method(attrs["method"])
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
    # Keirin permits dead heats. Equal numeric ranks are legitimate; do not
    # reject them unless the rider/car identity or source evidence conflicts.
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
    assert normalized_name("国井 裕樹") == normalized_name("國井裕樹")
    assert normalized_name("国井裕樹") != normalized_name("國村洋")
    assert normalized_prefecture("神奈") == "神奈川"
    assert normalized_prefecture("鹿児") == "鹿児島"
    assert normalized_prefecture("東京") != normalized_prefecture("神奈")
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
    b["results"][0]["method"] = "差し"
    a["results"][1]["method"] = "捲くり"
    b["results"][1]["method"] = "捲り"
    assert compare({"observations": [a, b]})["status"] == "SOURCE_CONTENT_MATCH_INDEPENDENCE_PENDING"
    b["results"][0]["finish"] = "2"
    b["results"][1]["finish"] = "1"
    assert compare({"observations": [a, b]})["status"] == "SOURCE_CONFLICT_REVIEW_REQUIRED"
    b["results"][0]["finish"] = "1"
    b["results"][1]["finish"] = "2"
    b["results"][1]["finish"] = "1"
    assert compare({"observations": [a, b]})["status"] == "SOURCE_CONFLICT_REVIEW_REQUIRED"
    a["results"][1]["finish"] = "1"
    assert compare({"observations": [a, b]})["status"] == "SOURCE_CONTENT_MATCH_INDEPENDENCE_PENDING"
    a["results"][1]["finish"] = "2"
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
    # Real publicly listed 2026-09-10 Keio-kaku 2R result: 7 finishers.
    # This fixture checks representation differences only, not source independence.
    actual = [
        (3, "田村光昭", "広島", "67", "1", "差"),
        (4, "篠田樹", "大分", "113", "2", "捲"),
        (5, "齋藤仁", "徳島", "83", "3", ""),
        (2, "深井高志", "東京", "63", "4", ""),
        (1, "相樂修", "千葉", "78", "5", ""),
        (6, "伊藤司", "福島", "83", "6", ""),
        (7, "山内大作", "静岡", "75", "7", ""),
    ]
    base = {"date": "2026-09-10", "trackCode": "27", "track": "京王閣",
            "race": 2, "className": "A3", "expectedCars": 7}
    observed_a = {"sourceUrl": "https://keirin.netkeiba.com/race/result/?race_id=202609102702",
                  "sourceId": "netkeirin-result", "race": dict(base),
                  "results": [{"number": c, "name": n, "prefecture": p, "period": k,
                               "finish": rank, "method": method, "exception": ""}
                              for c, n, p, k, rank, method in actual]}
    observed_b = {"sourceUrl": "https://www.lotoplace.jp/keirin/results/27/2026-09-10/",
                  "sourceId": "lotoplace-day-results", "race": dict(base),
                  "results": [{"number": c, "name": " ".join(list(n)),
                               "prefecture": p, "period": k, "finish": rank,
                               "method": {"差": "差し", "捲": "捲くり"}.get(method, method),
                               "exception": ""}
                              for c, n, p, k, rank, method in actual]}
    result = compare({"observations": [observed_a, observed_b]})
    assert result["carCount"] == 7 and result["status"] == "SOURCE_CONTENT_MATCH_INDEPENDENCE_PENDING"
    assert not result["formalPass"]
    print("SELF_TEST_OK: full-field match/conflict, missing car and same-domain guards")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input")
    p.add_argument("--left", help="One collected source observation JSON")
    p.add_argument("--right", help="Different collected source observation JSON")
    p.add_argument("--out")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input and (args.left or args.right):
        p.error("Use either --input or --left and --right")
    if args.input:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    elif args.left and args.right:
        payload = {"observations": [
            json.loads(Path(args.left).read_text(encoding="utf-8")),
            json.loads(Path(args.right).read_text(encoding="utf-8"))]}
    else:
        p.error("--input or both --left and --right required")
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
