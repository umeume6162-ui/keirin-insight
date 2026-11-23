#!/usr/bin/env python3
"""Bounded Tokyo Sports venue discovery; preview-only, not independent PASS.

Find the venue's 1R link on the public race list, follow its same-venue R
navigation (max 12), and validate every actual entry table before emitting JSON.
No Google writes and no inference of race identity from URL numbering.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from collect_tospo_entry import fetch, norm, parse

LIST_URL = "https://keirin.tokyo-sports.co.jp/list/race"
RACE_PATH = re.compile(r"^/list/race/[^/?#]+$")


def race_link(base, href):
    url = urljoin(base, href or "")
    u = urlsplit(url)
    if u.scheme == "https" and u.netloc == "keirin.tokyo-sports.co.jp" and RACE_PATH.fullmatch(u.path):
        return url
    return None


def discover(list_html, track, loader, date=None):
    """Use a venue-labelled index link, never numeric URL arithmetic."""
    doc = BeautifulSoup(list_html, "html.parser")
    starts = []
    for anchor in doc.select("a[href]"):
        url = race_link(LIST_URL, anchor.get("href"))
        label = norm(anchor.get_text(" ", strip=True))
        if url and track in label and re.search(r"(?<!\d)1\s*R(?!\d)", label):
            starts.append(url)
    if not starts:
        raise ValueError("Venue 1R not found on current public race list")
    if len(set(starts)) > 3:
        raise ValueError("Too many venue listings; manual review")
    # The index may mix yesterday/today/tomorrow; select by the event date
    # shown on the racecard, never lexicographically by URL.
    yyyy, mm, dd = date.split("-") if date else ("", "", "")
    matches = []
    for candidate in sorted(set(starts)):
        page = loader(candidate)
        if not date or re.search(
            rf"{int(yyyy)}年\s*{int(mm)}月\s*{int(dd)}日",
            norm(BeautifulSoup(page, "html.parser").get_text(" ", strip=True))
        ):
            matches.append((candidate, page))
    if len(matches) != 1:
        raise ValueError("Venue/date 1R not uniquely confirmed")
    first, page = matches[0]
    nav = BeautifulSoup(page, "html.parser")
    urls = {1: first}
    for a in nav.select("a[href]"):
        label = norm(a.get_text(" ", strip=True))
        m = re.match(r"^(\d{1,2})\s*R(?:\s|$)", label)
        url = race_link(first, a.get("href"))
        if not m or not url:
            continue
        race = int(m.group(1))
        if not 1 <= race <= 12:
            continue
        if race in urls and urls[race] != url:
            raise ValueError("Conflicting race navigation links")
        urls[race] = url
    return urls, {first: page}


def collect(date, track, code, list_html, loader):
    urls, cache = discover(list_html, track, loader, date)
    entries, failed = [], []
    for race, url in sorted(urls.items()):
        try:
            html = cache.get(url) or loader(url)
            entries.extend(parse(html, date, code, track, race, url))
        except (ValueError, RuntimeError) as exc:
            failed.append({"race": race, "error": str(exc)})
    if not entries:
        raise ValueError("No full racecard validated; do not treat as no races")
    return {"entries": entries, "results": [],
            "sourceNote": "Tokyo Sports preview; not independent PASS"}, failed


def self_test():
    # Synthetic index mirrors the site's venue-labelled 1R links.
    index = ('<a href="/list/race/20261122_31332">'
             'FⅡ 西武園 初日 1R 10:00発走</a>')
    page = ('<h1>西武園 2026年11月23日 1R</h1>'
            '<a href="/list/race/20261122_31333">2R A級戦</a>')
    urls, cache = discover(index, "西武園", lambda url: page, "2026-11-23")
    assert len(urls) == 2 and 1 in urls and 2 in urls
    assert len(cache) == 1
    try:
        discover(index, "前橋", lambda url: page)
    except ValueError:
        pass
    else:
        raise AssertionError("Accepted wrong venue")
    print("SELF_TEST_OK: venue index regex and bounded race navigation")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--date")
    p.add_argument("--track")
    p.add_argument("--track-code")
    p.add_argument("--out", default="/tmp/ki-tospo-discovery.json")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    if not all((a.date, a.track, a.track_code)):
        p.error("--date --track --track-code required")
    datetime.strptime(a.date, "%Y-%m-%d")
    if not (a.track_code.isdigit() and 1 <= int(a.track_code) <= 99):
        raise ValueError("Invalid track code")
    data, failed = collect(a.date, a.track, a.track_code, fetch(LIST_URL), fetch)
    Path(a.out).write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": "PREVIEW_ONLY", "races": len(set(
        x["race"] for x in data["entries"])), "entries": len(data["entries"]),
        "failed": failed, "out": a.out}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("NO_SAVE: " + str(exc), file=sys.stderr)
        sys.exit(1)
