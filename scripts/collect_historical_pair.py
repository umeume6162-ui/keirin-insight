#!/usr/bin/env python3
"""Collect exactly one race from netkeirin and Chariloto, compare as a candidate.

Reuse the existing source adapters and comparator. No Google writes, formal PASS,
GitHub mutations or credential access. Default URLs follow verified patterns.
"""
import argparse
import json
import sys
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
    right_url = right_url or (
        f"https://www.chariloto.com/keirin/results/{int(code)}/{day}"
    )
    netkeirin.validate_url(left_url, day, code, number)
    day_results.validate_url(right_url, day, code)
    left = netkeirin.extract(netkeirin.fetch(left_url), day, code, track,
                            number, class_name, cars, left_url)
    right = day_results.parse_result(day_results.fetch(right_url), day, code,
                                     track, number, class_name, cars, right_url)
    comparison = compare({"observations": [left, right]})
    assert comparison["formalPass"] is False
    return {"observations": [left, right], "comparison": comparison}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--track-code", required=True)
    parser.add_argument("--track", required=True)
    parser.add_argument("--race", required=True, type=int)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--expected-cars", required=True, type=int)
    parser.add_argument("--left-url", help="Optional verified netkeirin result URL")
    parser.add_argument("--right-url", help="Optional verified Chariloto/LotoPlace date URL")
    parser.add_argument("--out", required=True, help="One atomic candidate JSON artifact")
    args = parser.parse_args()
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
