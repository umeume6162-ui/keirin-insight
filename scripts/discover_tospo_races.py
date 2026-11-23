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

# Venue codes cross-checked against public 43-track stadium code list.
VENUE_CODES = {
    "函館":"11","青森":"12","いわき平":"13",
    "弥彦":"21","前橋":"22","取手":"23","宇都宮":"24","大宮":"25",
    "西武園":"26","京王閣":"27","立川":"28","松戸":"31","千葉":"32",
    "川崎":"34","平塚":"35","小田原":"36","伊東温泉":"37","静岡":"38",
    "名古屋":"42","岐阜":"43","大垣":"44","豊橋":"45","富山":"46",
    "松阪":"47","四日市":"48","福井":"51","奈良":"53","向日町":"54",
    "和歌山":"55","岸和田":"56","玉野":"61","広島":"62","防府":"63",
    "高松":"71","小松島":"73","高知":"74","松山":"75","小倉":"81",
    "久留米":"83","武雄":"84","佐世保":"85","別府":"86","熊本":"87"
}
# Only this known synonym is accepted; it is printed without 温泉 on some cards.
VENUE_ALIASES = {"伊東":"伊東温泉"}


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
        soup = BeautifulSoup(page, "html.parser")
        title = " ".join(norm(x.get_text(" ", strip=True)) for x in soup.select("title,h1"))
        if not date or (track in title and re.search(
            rf"{int(yyyy)}年\s*{int(mm)}月\s*{int(dd)}日", title
        )):
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



def list_venue_starts(list_html):
    """Find only explicit venue-labelled 1R index links, not unrelated site anchors."""
    soup = BeautifulSoup(list_html, "html.parser")
    discovered = {}
    for anchor in soup.select("a[href]"):
        url = race_link(LIST_URL, anchor.get("href"))
        label = norm(anchor.get_text(" ", strip=True))
        if not url or not re.search(r"(?<!\d)1\s*R(?!\d)", label):
            continue
        matches = []
        for name in VENUE_CODES:
            if re.search(r"(?<![一-龥])" + re.escape(name) + r"(?![一-龥])", label):
                matches.append(name)
        for alias, canonical in VENUE_ALIASES.items():
            if alias in label and canonical not in matches and canonical not in label:
                matches.append(canonical)
        if len(matches) != 1:
            continue
        name = matches[0]
        discovered.setdefault(name, set()).add(url)
    return {name: sorted(urls) for name, urls in sorted(discovered.items())}


def collect_venues(day, list_html, loader, max_venues=3):
    """Bounded single-index preview; no network writes and no empty=zero-races claim."""
    if not 1 <= max_venues <= 12:
        raise ValueError("max_venues must be 1..12")
    datetime.strptime(day, "%Y-%m-%d")
    listing = list_venue_starts(list_html)
    if not listing:
        raise ValueError("No venue-labelled 1R links; source unavailable, not no races")
    entries, failures, verified = [], [], []
    for name in list(listing)[:max_venues]:
        try:
            # Discover verifies the requested date on each venue's racecard.
            payload, missing = collect(day, name, VENUE_CODES[name], list_html, loader)
            entries.extend(payload["entries"])
            failures.extend([{"track": name, **x} for x in missing])
            verified.append(name)
        except (ValueError, RuntimeError) as exc:
            failures.append({"track": name, "reason": type(exc).__name__})
    if not entries:
        raise ValueError("No full seven/nine-car racecard validated for chosen date")
    unique = set()
    for record in entries:
        key = (record["date"], record["trackCode"], record["race"], record["number"])
        if key in unique:
            raise ValueError("Duplicate venue/race/car identity")
        unique.add(key)
    return {"entries": entries, "results": [],
            "sourceNote": "Multi-venue Tokyo Sports preview only; not independent PASS"}, {
                "listedVenues": len(listing), "examinedVenues": min(len(listing), max_venues),
                "validatedVenues": verified, "failed": failures,
                "truncated": len(listing) > max_venues
            }


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
    assert len(VENUE_CODES) == 43 and len(set(VENUE_CODES.values())) == 43
    listing = ('<a href="/list/race/20261123_30926">FⅠ 静岡 初日 1R 11:05</a>'
               '<a href="/list/race/20261122_31332">FⅡ 西武園 ２日目 1R 10:00</a>')
    found = list_venue_starts(listing)
    assert set(found) == {"静岡", "西武園"}
    assert found["静岡"] == ["https://keirin.tokyo-sports.co.jp/list/race/20261123_30926"]
    # Mismatching all dates must fail closed without a fake 'no races' result.
    try:
        collect_venues("2026-11-24", listing, lambda u: "<h1>2026年11月22日 西武園 1R</h1>", 2)
    except ValueError:
        pass
    else:
        raise AssertionError("Wrong-day venue list accepted")
    print("SELF_TEST_OK: venue index regex and bounded race navigation")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--date")
    p.add_argument("--track")
    p.add_argument("--track-code")
    p.add_argument("--all-venues", action="store_true")
    p.add_argument("--max-venues", type=int, default=3)
    p.add_argument("--out", default="/tmp/ki-tospo-discovery.json")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    if not a.date or (not a.all_venues and not all((a.track,a.track_code))):
        p.error("--date and (--all-venues or --track --track-code) required")
    datetime.strptime(a.date, "%Y-%m-%d")
    if not a.all_venues and not (a.track_code.isdigit() and 1 <= int(a.track_code) <= 99):
        raise ValueError("Invalid track code")
    data, report = (collect_venues(a.date, fetch(LIST_URL), fetch, a.max_venues)
                    if a.all_venues else collect(a.date, a.track, a.track_code, fetch(LIST_URL), fetch))
    failed = report if a.all_venues else report
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
