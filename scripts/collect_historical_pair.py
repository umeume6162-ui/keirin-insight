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



class SourceStageError(ValueError):
    """Sanitized source location; original exception available as __cause__."""

    def __init__(self, source_stage):
        super().__init__("Result source observation unavailable")
        self.source_stage = source_stage



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
    try:
        left = netkeirin.extract(netkeirin.fetch(left_url), day, code, track,
                                number, class_name, cars, left_url)
    except (ValueError, requests.exceptions.RequestException) as exc:
        if explicit_right_url or left_url != (
                "https://keirin.netkeiba.com/race/result/?race_id="
                + day.replace("-", "") + code + str(number).zfill(2)):
            # An explicitly selected source pair must never be silently replaced.
            raise SourceStageError("PRIMARY_NETKEIRIN") from exc
        # V99 collected Chariloto HTML directly. If netkeirin cannot supply a
        # full result, try the two OTHER permitted public publications, each
        # with its own robots gate and a complete 7/9-car source parser.
        alt_url = f"https://www.lotoplace.jp/keirin/results/{int(code)}/{day}/"
        try:
            day_results.validate_url(alt_url, day, code)
            first = day_results.parse_result(day_results.fetch(right_url), day, code,
                                             track, number, class_name, cars, right_url)
            second = day_results.parse_result(day_results.fetch(alt_url), day, code,
                                              track, number, class_name, cars, alt_url)
        except (ValueError, requests.exceptions.RequestException) as alt_exc:
            raise SourceStageError("ALTERNATE_PAIR_UNAVAILABLE") from alt_exc
        # Keep content disagreement distinct from a source outage.
        alt_comparison = compare({"observations": [first, second]})
        assert alt_comparison["formalPass"] is False
        return {"observations": [first, second],
                "comparison": alt_comparison,
                "sourcePairMode": "CHARILOTO_LOTOPLACE_FALLBACK"}
    try:
        right = day_results.parse_result(day_results.fetch(right_url), day, code,
                                         track, number, class_name, cars, right_url)
    except (ValueError, requests.exceptions.RequestException) as exc:
        if explicit_right_url:
            # Never silently replace a user-verified right source URL.
            raise SourceStageError("SECONDARY_EXPLICIT") from exc
        alternate = f"https://www.lotoplace.jp/keirin/results/{int(code)}/{day}/"
        try:
            day_results.validate_url(alternate, day, code)
            right = day_results.parse_result(day_results.fetch(alternate), day, code,
                                             track, number, class_name, cars, alternate)
        except (ValueError, requests.exceptions.RequestException) as fallback_exc:
            raise SourceStageError("SECONDARY_BOTH_UNAVAILABLE") from fallback_exc
    comparison = compare({"observations": [left, right]})
    assert comparison["formalPass"] is False
    return {"observations": [left, right], "comparison": comparison}



def collect_auto(day, code, track, number, class_name, cars, sources=None):
    """Compare any two available validated result publications, not a fixed primary.

    The default pool currently contains three supported adapters. New publicly
    permitted source adapters can be added without changing the pair selector.
    Each source is fetched at most once. Full-field validation, two distinct
    publication hosts and rider identity are enforced downstream by compare().
    This is not unrestricted website scraping or proof of upstream independence.
    """
    date.fromisoformat(day)
    if (not day.startswith("20") or not code.isdigit()
            or not 1 <= int(code) <= 99 or not track.strip()
            or not 1 <= number <= 12 or cars not in (7, 9)):
        raise ValueError("Invalid race identity or expected car count")
    code = code.zfill(2)
    if sources is None:
        net_url = ("https://keirin.netkeiba.com/race/result/?race_id="
                   + day.replace("-", "") + code + str(number).zfill(2))
        char_url = f"https://www.chariloto.com/keirin/results/{int(code)}/{day}"
        loto_url = f"https://www.lotoplace.jp/keirin/results/{int(code)}/{day}/"

        def read_net():
            netkeirin.validate_url(net_url, day, code, number)
            return netkeirin.extract(netkeirin.fetch(net_url), day, code, track,
                                    number, class_name, cars, net_url)

        def read_day(url):
            day_results.validate_url(url, day, code)
            return day_results.parse_result(day_results.fetch(url), day, code,
                                            track, number, class_name, cars, url)

        sources = (("netkeirin", read_net),
                   ("chariloto", lambda: read_day(char_url)),
                   ("lotoplace", lambda: read_day(loto_url)))
    if not sources or len(sources) > 12:
        raise ValueError("Invalid bounded result source pool")
    collected = []
    matched = None
    source_failed = 0
    for source_name, read_source in sources:
        if not callable(read_source) or not isinstance(source_name, str):
            raise ValueError("Invalid result source adapter")
        try:
            observation = read_source()
        except (ValueError, requests.exceptions.RequestException):
            source_failed += 1
            continue
        # Recompute every pair, including when earlier publications disagreed.
        for earlier in collected:
            candidate = {"observations": [earlier, observation]}
            try:
                comparison = compare(candidate)
            except ValueError:
                continue
            if (comparison["status"] == "SOURCE_CONTENT_MATCH_INDEPENDENCE_PENDING"
                    and comparison["formalPass"] is False
                    and not comparison["disagreements"]):
                matched = {**candidate, "comparison": comparison,
                           "sourcePairMode": "SOURCE_POOL_MATCH"}
                break
        if matched:
            break
        collected.append(observation)
    if matched:
        return matched
    if len(collected) < 2:
        raise SourceStageError("SOURCE_POOL_UNAVAILABLE")
    raise ValueError("Two result publications do not agree")


def self_test_auto():
    race = dict(date="2026-09-10", trackCode="27", track="京王閣",
                race=2, className="A3", expectedCars=7)
    rows = [dict(number=n, name=f"選手 {n}", prefecture="東京", period="90",
                 finish=str(n), method="差" if n == 1 else "", exception="")
            for n in range(1, 8)]
    def make(host, sid, altered=False):
        rr = [dict(x) for x in rows]
        if altered:
            rr[0]["finish"] = "2"
        return dict(sourceUrl=f"https://{host}/race/result/20260910/2",
                    sourceId=sid, race=dict(race), results=rr)
    net = make("source-a.example", "net")
    official = make("venue.example", "official")
    journalist = make("press.example", "press")
    calls = []
    def read(label, obj):
        def run():
            calls.append(label)
            if obj is None:
                raise ValueError("source unavailable")
            return obj
        return run
    default = [("first", read("first", None)),
               ("venue", read("venue", official)),
               ("press", read("press", journalist))]
    report = collect_auto("2026-09-10", "27", "京王閣", 2, "A3", 7,
                          sources=default)
    assert report["sourcePairMode"] == "SOURCE_POOL_MATCH"
    assert report["comparison"]["formalPass"] is False
    assert calls == ["first", "venue", "press"]
    changed = make("source-a.example", "net", altered=True)
    calls.clear()
    report2 = collect_auto("2026-09-10", "27", "京王閣", 2, "A3", 7,
                           sources=[("a", read("a", changed)),
                                    ("b", read("b", official)),
                                    ("c", read("c", journalist))])
    assert report2["comparison"]["status"] == "SOURCE_CONTENT_MATCH_INDEPENDENCE_PENDING"
    assert calls == ["a", "b", "c"]
    try:
        collect_auto("2026-09-10", "27", "京王閣", 2, "A3", 7,
                     sources=[("only", read("only", net)),
                              ("missing", read("missing", None))])
    except SourceStageError as e:
        assert e.source_stage == "SOURCE_POOL_UNAVAILABLE"
    else:
        raise AssertionError("Single source was accepted")
    print("SELF_TEST_OK: publisher-neutral bounded result pool and full-field matching")


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
        except SourceStageError as exc:
            assert exc.source_stage == "SECONDARY_EXPLICIT"
            assert isinstance(exc.__cause__, ValueError)
        else:
            raise AssertionError("Explicit right URL was silently changed")
        assert fetched.call_count == 1
    with (patch.object(netkeirin, "fetch", side_effect=ValueError("Robots rules prohibit this page")),
          patch.object(day_results, "fetch", return_value="html") as fetched,
          patch.object(day_results, "parse_result", side_effect=read_right) as parsed):
        try:
            collect(day, code, track, number, cls, cars)
        except SourceStageError as exc:
            assert exc.source_stage == "ALTERNATE_PAIR_UNAVAILABLE"
        else:
            raise AssertionError("Incomplete alternate pair was accepted")
        assert fetched.call_count == 1 and parsed.call_count == 1
    alt_obs = {"sourceUrl": f"https://www.lotoplace.jp/keirin/results/27/{day}/",
               "sourceId": "lotoplace-day-results"}
    char_obs = {"sourceUrl": f"https://www.chariloto.com/keirin/results/27/{day}",
                "sourceId": "chariloto-day-results"}
    with (patch.object(netkeirin, "fetch", side_effect=ValueError("Robots rules prohibit this page")),
          patch.object(day_results, "fetch", return_value="html") as fetched,
          patch.object(day_results, "parse_result", side_effect=[char_obs, alt_obs]),
          patch(__name__ + ".compare", return_value=comparison)):
        fallback = collect(day, code, track, number, cls, cars)
        assert fallback["sourcePairMode"] == "CHARILOTO_LOTOPLACE_FALLBACK"
        assert fallback["comparison"]["formalPass"] is False
        assert fetched.call_count == 2
    with (patch.object(netkeirin, "fetch", side_effect=ValueError("Robots rules prohibit this page")),
          patch.object(day_results, "fetch") as second):
        try:
            collect(day, code, track, number, cls, cars,
                    right_url=f"https://www.chariloto.com/keirin/results/27/{day}")
        except SourceStageError as exc:
            assert exc.source_stage == "PRIMARY_NETKEIRIN"
        else:
            raise AssertionError("Explicit source pair was silently replaced")
        second.assert_not_called()
    with (patch.object(netkeirin, "fetch", return_value="html"),
          patch.object(netkeirin, "extract", return_value=left_obs),
          patch.object(day_results, "fetch", side_effect=ValueError("No results"))):
        try:
            collect(day, code, track, number, cls, cars)
        except SourceStageError as exc:
            assert exc.source_stage == "SECONDARY_BOTH_UNAVAILABLE"
        else:
            raise AssertionError("Fallback failures were not classified")
    self_test_auto()
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
