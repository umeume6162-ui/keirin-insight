#!/usr/bin/env python3
"""Daily Tokyo Sports racecards -> scoped, idempotent Google Sheets upserts.

Discover *listed* venues once, and process each venue independently (up to
12 races / 108 rider rows per write). Never mistake absent data for no races.
If one venue has a source error or conflicts with existing rows, report it
and continue with the remaining venues. No edits to verified feeds or V99.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from collect_tospo_entry import fetch
from discover_tospo_races import LIST_URL, VENUE_CODES, collect, list_venue_starts
from upsert_daily_sheets import apply, prepare

APPROVED_EDITOR = "keirin-insight-sheets-reader@possible-helix-433523-q9.iam.gserviceaccount.com"
JST = ZoneInfo("Asia/Tokyo")
MAX_VENUES = len(VENUE_CODES)
MAX_ROWS_PER_VENUE = 12 * 9


def verify_approved_editor():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise ValueError("No Sheets credential; no write")
    try:
        if json.loads(raw).get("client_email") != APPROVED_EDITOR:
            raise ValueError("Sheets editor identity mismatch; no write")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Sheets credential; no write") from exc


def check_venue_payload(day, track, data):
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_ROWS_PER_VENUE:
        raise ValueError("Empty or oversized venue payload")
    if data.get("results") != []:
        raise ValueError("Unexpected result payload")
    if any(x.get("date") != day or x.get("track") != track or
           str(x.get("trackCode")) != VENUE_CODES[track] for x in entries):
        raise ValueError("Incorrect date/venue on card")
    grouped = defaultdict(set)
    for row in entries:
        race = row.get("race")
        car = row.get("number")
        if type(race) is not int or not 1 <= race <= 12 or type(car) is not int:
            raise ValueError("Invalid race/car")
        if car in grouped[race]:
            raise ValueError("Duplicate car in race")
        grouped[race].add(car)
    if len(grouped) > 12 or any(cars not in (set(range(1, 8)), set(range(1, 10)))
                               for cars in grouped.values()):
        raise ValueError("Incomplete racecard; no write")
    normalized = prepare(data)
    if len(normalized["entries"]) != len(entries) or normalized["results"]:
        raise ValueError("Duplicate identity after normalization")
    return len(grouped)


def run(day, index_html, loader=fetch, max_venues=MAX_VENUES, write=False):
    """Process the public venue index without a *daily total* race cap.

    max_venues applies only to the index enumeration, not to race rows. Each
    venue is independently checked, compared and appended. The summary
    exposes incomplete coverage rather than claiming a complete schedule.
    """
    if not 1 <= max_venues <= MAX_VENUES:
        raise ValueError("max_venues out of range")
    datetime.strptime(day, "%Y-%m-%d")
    listing = list_venue_starts(index_html)
    if not listing:
        return {"day": day, "status": "INDEX_UNAVAILABLE_OR_EMPTY",
                "listedVenues": 0, "coverageComplete": False, "venues": []}
    if write:
        verify_approved_editor()
    names = list(listing)
    selected = names[:max_venues]
    details = []
    for track in selected:
        record = {"track": track, "trackCode": VENUE_CODES[track], "saved": False}
        try:
            payload, missing = collect(day, track, VENUE_CODES[track], index_html, loader)
            race_count = check_venue_payload(day, track, payload)
            dry = apply(payload, dry_run=True)
            summary = dry["summary"]["entries"]
            record.update({"races": race_count, "entries": len(payload["entries"]),
                           "new": summary["new"], "unchanged": summary["unchanged"],
                           "changed": summary["changed"], "incompleteRaces": len(missing)})
            if summary["changed"] or (dry["summary"]["results"]["new"] or
                                      dry["summary"]["results"]["changed"]):
                record["status"] = "CONFLICT_REVIEW_NO_WRITE"
            elif not write:
                record["status"] = "DRY_RUN"
            elif not summary["new"]:
                record["status"] = "UNCHANGED_NO_WRITE"
            else:
                saved = apply(payload, dry_run=False)
                saved_entries = saved["summary"]["entries"]
                if (saved_entries["new"] != summary["new"] or
                        saved_entries["changed"] != 0):
                    raise RuntimeError("Actual write differs from dry-run")
                record.update({"status": "SAVED_UNVERIFIED_ENTRIES", "saved": True})
        except Exception as exc:
            # Never emit credentials, raw pages, or arbitrary URL contents.
            record.update({"status": "SOURCE_OR_WRITE_ERROR_REVIEW",
                           "errorType": type(exc).__name__})
        details.append(record)
    counts = {"races": sum(x.get("races", 0) for x in details),
              "entries": sum(x.get("entries", 0) for x in details),
              "new": sum(x.get("new", 0) for x in details if x.get("saved")),
              "incompleteRaces": sum(x.get("incompleteRaces", 0) for x in details)}
    complete = (len(selected) == len(names) and
                all(x["status"] in ("DRY_RUN", "UNCHANGED_NO_WRITE",
                                   "SAVED_UNVERIFIED_ENTRIES") and
                    x.get("incompleteRaces", 0) == 0 for x in details))
    return {"day": day, "status": "VENUE_SCOPED_INTAKE",
            "listedVenues": len(names), "examinedVenues": len(selected),
            "coverageComplete": complete, "counts": counts, "venues": details,
            "formalPass": False}


def self_test():
    from unittest.mock import patch
    from types import SimpleNamespace
    mod = sys.modules[__name__]
    assert MAX_VENUES == 43 and MAX_ROWS_PER_VENUE == 108
    try:
        verify_approved_editor()
    except ValueError:
        pass
    else:
        if "GOOGLE_SERVICE_ACCOUNT_JSON" not in os.environ:
            raise AssertionError("Missing credential accepted")
    race_list = ('<a href="/list/race/a">FⅠ 静岡 1R</a>'
                 '<a href="/list/race/b">FⅡ 松山 1R</a>'
                 '<a href="/list/race/c">FⅡ 前橋 1R</a>'
                 '<a href="/list/race/d">FⅡ 奈良 1R</a>')
    def fake_collect(day, track, code, html, loader):
        rows = [{"date": day, "track": track, "trackCode": code,
                 "race": race, "number": car, "name": "選手"}
                for race in range(1, 13) for car in range(1, 8)]
        return {"entries": rows, "results": []}, []
    def fake_prepare(data):
        return {"entries": {str(i): row for i, row in enumerate(data["entries"])},
                "results": {}}
    observed = []
    def fake_apply(data, dry_run=True):
        track = data["entries"][0]["track"]
        observed.append((track, dry_run))
        changed = 1 if track == "松山" else 0
        return {"summary": {"entries":{"new":84 if dry_run else 84,
                                       "changed":changed,"unchanged":0},
                            "results":{"new":0,"changed":0}}}
    with (patch.object(mod, "collect", side_effect=fake_collect),
          patch.object(mod, "prepare", side_effect=fake_prepare),
          patch.object(mod, "apply", side_effect=fake_apply),
          patch.object(mod, "verify_approved_editor", return_value=None)):
        result = run("2026-11-24", race_list, max_venues=43, write=True)
    assert result["listedVenues"] == 4 and result["counts"]["races"] == 48
    by_track = {x["track"]: x for x in result["venues"]}
    assert by_track["静岡"]["saved"] and not by_track["松山"]["saved"]
    assert result["counts"]["new"] == 252 and not result["coverageComplete"]
    assert observed.count(("静岡", True)) == 1
    assert observed.count(("静岡", False)) == 1
    assert observed.count(("松山", True)) == 1
    assert ("松山", False) not in observed
    assert run("2026-11-24", "<p>no race links</p>")["status"] == "INDEX_UNAVAILABLE_OR_EMPTY"
    print("SELF_TEST_OK: 48R across four venues, isolated writes, conflict skip and incomplete coverage")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--max-venues", type=int, default=MAX_VENUES)
    p.add_argument("--days", type=int, choices=(1, 2), default=2)
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    start = datetime.now(JST).date()
    index = fetch(LIST_URL)
    reports = [run((start + timedelta(days=n)).isoformat(), index,
                   max_venues=args.max_venues, write=args.apply)
               for n in range(args.days)]
    print(json.dumps({"schema": "ki-daily-auto-intake-report-v2",
                      "formalPass": False, "results": reports}, ensure_ascii=False))
    if any(not r.get("coverageComplete") for r in reports):
        print("DAILY_AUTO_WARNING: incomplete venue coverage; do not infer no races",
              file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("DAILY_AUTO_ABORT: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
