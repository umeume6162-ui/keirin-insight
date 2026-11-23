#!/usr/bin/env python3
"""Collect exactly one race from netkeirin and Chariloto, compare as a candidate.

Reuse the existing source adapters and comparator. No Google writes, formal PASS,
GitHub mutations or credential access. Default URLs follow verified patterns.
"""
import argparse
import json
import sys
from unittest.mock import patch

import requests
from datetime import date
from pathlib import Path

import collect_netkeirin_result as netkeirin
import collect_lotoplace_result as day_results
from compare_race_results import compare


def collect(day, code, track, number, class_name, cars, left_url=None, right_url=None):
    date.fromisoformat(day)
    if not day.startswith("20") or not code.isdigit() or not 1 <= int(code) <= 99:
        raise ValueError("Invalid date or track code")
    if not 1 <= number <= 12 or cars not in (7, 9) or not track.strip():
        raise ValueError("Invalid race identity or expected car count")
    code = code.zfill(2)
    left_url = left_url or (
        "https://keirin.netkeiba.com/race/result/?race_id="
        + day.replace("-", "") + code + str(number).zfill(2)
    )
    explicit_right_url = right_url is not None
    right_url = right_url or (
        f"https://www.chariloto.com/keirin/results/{int(code)}/{day}"
    )
    netkeirin.validate_url(left_url, day, code, number)
    day_results.validate_url(right_url, day, code)
    left = netkeirin.extract(netkeirin.fetch(left_url), day, code, track,
                            number, class_name, cars, left_url)
    try:
        right = day_results.parse_result(day_results.fetch(right_url), day, code,
                                         track, number, class_name, cars, right_url)
    except (ValueError, requests.exceptions.RequestException):
        if explicit_right_url:
            # Never silently replace a user-verified right source URL.
            raise
        alternate = f"https://www.lotoplace.jp/keirin/results/{int(code)}/{day}/"
        day_results.validate_url(alternate, day, code)
        right = day_results.parse_result(day_results.fetch(alternate), day, code,
                                         track, number, class_name, cars, alternate)
    comparison = compare({"observations": [left, right]})
    assert comparison["formalPass"] is False
    return {"observations": [left, right], "comparison": comparison}



def self_test():
    day, code, track, number, cls, cars = "2026-09-10", "27", "京王閣", 2, "A3", 7
    left_obs = {"sourceUrl": "https://keirin.netkeiba.com/race/result/?race_id=202609102702",
                "sourceId": "netkeirin-result"}
    def read_right(_html, _day, _code, _track, _number, _cls, _cars, url):
        if "chariloto.com" in url:
            raise ValueError("Exactly one complete target-race result table required")
        return {"sourceUrl": url, "sourceId": "lotoplace-day-results"}
    comparison = {"formalPass": False, "raceKey": "2026-09-10|27|2"}
    with (patch.object(netkeirin, "fetch", return_value="html"),
          patch.object(netkeirin, "extract", return_value=left_obs),
          patch.object(day_results, "fetch", return_value="html") as fetched,
          patch.object(day_results, "parse_result", side_effect=read_right),
          patch(__name__ + ".compare", return_value=comparison)):
        result = collect(day, code, track, number, cls, cars)
        assert result["comparison"]["formalPass"] is False
        assert result["observations"][1]["sourceUrl"].startswith("https://www.lotoplace.jp/")
        assert fetched.call_count == 2
    custom = f"https://www.chariloto.com/keirin/results/27/{day}"
    with (patch.object(netkeirin, "fetch", return_value="html"),
          patch.object(netkeirin, "extract", return_value=left_obs),
          patch.object(day_results, "fetch", return_value="html") as fetched,
          patch.object(day_results, "parse_result", side_effect=read_right)):
        try:
            collect(day, code, track, number, cls, cars, right_url=custom)
        except ValueError:
            pass
        else:
            raise AssertionError("Explicit right URL was silently changed")
        assert fetched.call_count == 1
    print("SELF_TEST_OK: bounded second-source fallback, explicit URL unchanged, no formal PASS")



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--date", required=False)
    parser.add_argument("--track-code", required=False)
    parser.add_argument("--track", required=False)
    parser.add_argument("--race", required=False, type=int)
    parser.add_argument("--class-name", required=False)
    parser.add_argument("--expected-cars", required=False, type=int)
    parser.add_argument("--left-url", help="Optional verified netkeirin result URL")
    parser.add_argument("--right-url", help="Optional verified Chariloto/LotoPlace date URL")
    parser.add_argument("--out", required=False, help="One atomic candidate JSON artifact")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not all((args.date, args.track_code, args.track, args.race, args.class_name, args.expected_cars, args.out)):
        parser.error("race metadata and --out are required except with --self-test")
    result = collect(args.date, args.track_code, args.track, args.race,
                     args.class_name, args.expected_cars, args.left_url,
                     args.right_url)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({
        "status": result["comparison"]["status"],
        "raceKey": result["comparison"]["raceKey"],
        "cars": result["comparison"]["carCount"],
        "disagreements": len(result["comparison"]["disagreements"]),
        "formalPass": False,
        "output": str(output)
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("NO_SAVE: " + str(exc), file=sys.stderr)
        sys.exit(1)
