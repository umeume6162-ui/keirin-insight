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


def discover(list_html, track, loader):
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
    if len(set(starts)) > 2:
        raise ValueError("Ambiguous multiple venue listings; manual review")
    # Each page may expose a full same-day race navigation. Bound requests and
    # leave identity proof to the racecard parser.
    first = sorted(set(starts))[0]
    page = loader(first)
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
    urls, cache = discover(list_html, track, loader)
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--track", required=True)
    p.add_argument("--track-code", required=True)
    p.add_argument("--out", default="/tmp/ki-tospo-discovery.json")
    a = p.parse_args()
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
