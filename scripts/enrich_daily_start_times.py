#!/usr/bin/env python3
"""Source-checked race start times for the unverified daily viewing feed.

Does not edit Google Sheets, verified data, or race outcomes. Only explicit
"発走：HH:MM" in the race-detail header of a fully matched public racecard
is used. A small source-URL-and-riders-bound cache survives daily feed
rebuilds; changed rider lists or source links force a new verification.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from collect_tospo_entry import fetch, norm, parse
from discover_tospo_races import VENUE_CODES

SCHEMA = "ki-daily-start-times-v1"
START_RE = re.compile(r"^発走\s*[:：]\s*((?:[01]\d|2[0-3]):[0-5]\d)$")


def source_identity(race):
    entries = race.get("entries", [])
    if len(entries) not in (7, 9):
        return None
    if (not isinstance(race.get("race"), int) or
            not isinstance(race.get("date"), str) or
            race.get("track") not in VENUE_CODES):
        return None
    if sorted(x.get("number") for x in entries) != list(range(1, len(entries) + 1)):
        return None
    urls = {x.get("sourceUrl") for x in entries}
    if len(urls) != 1:
        return None
    url = next(iter(urls))
    if not isinstance(url, str) or not url.startswith("https://keirin.tokyo-sports.co.jp/list/race/"):
        return None
    identity = [[x["number"], norm(x.get("name"))] for x in sorted(entries, key=lambda e:e["number"])]
    if any(len(x[1]) < 2 for x in identity):
        return None
    signature = hashlib.sha256(json.dumps(
        [race["date"], race["track"], race["race"], url, identity],
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return url, signature


def parse_start(html, race, url):
    track = race["track"]
    code = VENUE_CODES[track]
    rows = parse(html, race["date"], code, track, race["race"], url)
    old = {x["number"]: norm(x["name"]) for x in race["entries"]}
    if len(rows) != len(old) or any(old.get(x["number"]) != norm(x["name"]) for x in rows):
        raise ValueError("Rider identity changed; do not publish time")
    soup = BeautifulSoup(html, "html.parser")
    elements = soup.select(".race-detail__start")
    if len(elements) != 1:
        raise ValueError("Race header start time missing or ambiguous")
    text = norm(elements[0].get_text(" ", strip=True))
    match = START_RE.fullmatch(text)
    if not match:
        raise ValueError("Race start time invalid or ambiguous")
    return match.group(1)


def enrich(board, cache, loader=fetch, limit=24):
    if board.get("schema") != "ki-daily-board-v1" or not isinstance(board.get("races"), list):
        raise ValueError("Unrecognized daily feed schema")
    if cache.get("schema") != SCHEMA or not isinstance(cache.get("races"), dict):
        raise ValueError("Unrecognized start-time cache")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    old = cache["races"]
    updated = {}
    stats = {"cached": 0, "fetched": 0, "held": 0, "notApplicable": 0}
    # Do not reuse an old start time from the generated feed if the provenance
    # cannot be revalidated against this current complete racecard.
    eligible = []
    for race in board["races"]:
        race.pop("startTime", None)
        race.pop("startTimeSourceUrl", None)
        ident = source_identity(race)
        if ident is None:
            stats["notApplicable"] += 1
            continue
        url, signature = ident
        key = race.get("key")
        saved = old.get(key)
        if (isinstance(saved, dict) and
                saved.get("sourceUrl") == url and
                saved.get("signature") == signature and
                START_RE.fullmatch("発走：" + str(saved.get("startTime", "")))):
            race["startTime"] = saved["startTime"]
            race["startTimeSourceUrl"] = url
            updated[key] = saved
            stats["cached"] += 1
        else:
            eligible.append((race, url, signature))
    eligible.sort(key=lambda t: (t[0]["date"], t[0]["track"], t[0]["race"]), reverse=True)
    for race, url, signature in eligible[:limit]:
        try:
            time = parse_start(loader(url), race, url)
            race["startTime"] = time
            race["startTimeSourceUrl"] = url
            updated[race["key"]] = {"startTime": time, "sourceUrl": url,
                                    "signature": signature}
            stats["fetched"] += 1
        except Exception:
            # Absence / source errors are held; never infer start times from
            # race number, another venue's navigation, or a prior meeting.
            stats["held"] += 1
    stats["deferred"] = max(0, len(eligible) - limit)
    cache["races"] = dict(sorted(updated.items()))
    return stats


def self_test():
    day = "2026-11-24"
    url = "https://keirin.tokyo-sports.co.jp/list/race/one"
    race = {"key": day+"|静岡|1", "date": day, "track": "静岡", "race": 1,
            "entries": [{"number": i, "name": f"テスト選手{i}", "sourceUrl": url}
                        for i in range(1, 8)]}
    header = "<title>2026年11月24日 静岡競輪 1R 出走表</title>"
    table = "<table><tr><th>車番</th><th>選手名</th><th>級 脚</th></tr>" + "".join(
        f"<tr><td>{i}</td><td>テスト選手{i} 40歳 / 静岡 / 100期</td><td>Ａ３ 両</td></tr>"
        for i in range(1, 8)) + "</table>"
    html = header + "<div class='race-detail__start'>発走：11:05</div>" + table
    board = {"schema": "ki-daily-board-v1", "races": [race]}
    cache = {"schema": SCHEMA, "races": {}}
    count = [0]
    def loader(_):
        count[0] += 1
        return html
    stats = enrich(board, cache, loader, 2)
    assert stats["fetched"] == 1 and race["startTime"] == "11:05"
    assert cache["races"][race["key"]]["sourceUrl"] == url
    again = enrich(board, cache, lambda _: (_ for _ in ()).throw(AssertionError("no fetch")), 2)
    assert again["cached"] == 1 and count == [1]
    race["entries"][0]["name"] = "別の選手"
    hold = enrich(board, cache, loader, 2)
    assert hold["held"] == 1 and "startTime" not in race
    assert not cache["races"]
    print("SELF_TEST_OK: sourced start time, validated cache, stale rider change withheld")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--feed", default="daily-board-feed-v1.json")
    p.add_argument("--cache", default="daily-race-start-times-v1.json")
    p.add_argument("--limit", type=int, default=24)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    feed_path, cache_path = Path(args.feed), Path(args.cache)
    board = json.loads(feed_path.read_text(encoding="utf-8"))
    cache = (json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists()
             else {"schema": SCHEMA, "races": {}})
    stats = enrich(board, cache, limit=args.limit)
    feed_content = json.dumps(board, ensure_ascii=False, indent=2) + "\n"
    cache_content = json.dumps(cache, ensure_ascii=False, indent=2) + "\n"
    if feed_path.read_text(encoding="utf-8") != feed_content:
        feed_path.write_text(feed_content, encoding="utf-8")
    if not cache_path.exists() or cache_path.read_text(encoding="utf-8") != cache_content:
        cache_path.write_text(cache_content, encoding="utf-8")
    print("DAILY_START_TIME_ENRICH", json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("DAILY_START_TIME_ABORT:", type(exc).__name__, str(exc), file=sys.stderr)
        sys.exit(1)
