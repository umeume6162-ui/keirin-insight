#!/usr/bin/env python3
"""Bounded daily Tokyo Sports entries -> existing Sheets upsert.

The index is fetched once, only explicitly listed venues are examined.
Reads today/tomorrow (JST), refuses changed existing rows, and never edits
V99/verified feeds. Default: dry-run. Explicit --apply for scheduled writes.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from collect_tospo_entry import fetch
from discover_tospo_races import LIST_URL, VENUE_CODES, collect_venues
from upsert_daily_sheets import apply, prepare

APPROVED_EDITOR = "keirin-insight-sheets-reader@possible-helix-433523-q9.iam.gserviceaccount.com"
JST = ZoneInfo("Asia/Tokyo")


def verify_approved_editor():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise ValueError("No Sheets credential; no write")
    try:
        if json.loads(raw).get("client_email") != APPROVED_EDITOR:
            raise ValueError("Sheets editor identity mismatch; no write")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Sheets credential; no write") from exc


def run(day, index_html, loader=fetch, max_venues=8, write=False):
    # Count the requested race dates independently, never assume missing=0 races.
    report = {"day": day, "saved": False}
    try:
        data, discovery = collect_venues(day, index_html, loader, max_venues)
    except (ValueError, RuntimeError) as exc:
        return {**report, "status": "SOURCE_UNAVAILABLE_OR_NO_VALID_RACECARD",
                "reason": type(exc).__name__}
    entries = data["entries"]
    if not entries or len(entries) > 288:
        return {**report, "status": "REVIEW_UNBOUNDED_OR_EMPTY_BATCH"}
    if any(x["date"] != day or x["trackCode"] not in VENUE_CODES.values() for x in entries):
        raise ValueError("Unexpected venue/date in source payload")
    prepared = prepare(data)
    if len(prepared["entries"]) != len(entries) or prepared["results"]:
        raise ValueError("Duplicate race/car or unexpected result payload")
    dry = apply(data, dry_run=True)
    summary = dry["summary"]["entries"]
    report.update({"status": "DRY_RUN", "entries": len(entries),
                   "new": summary["new"], "changed": summary["changed"],
                   "unchanged": summary["unchanged"],
                   "validatedVenues": discovery["validatedVenues"],
                   "failedVenueCount": len(discovery["failed"]),
                   "truncated": discovery["truncated"]})
    if summary["changed"] or dry["summary"]["results"]["new"] or dry["summary"]["results"]["changed"]:
        report["status"] = "EXISTING_ROWS_CONFLICT_REVIEW"
        return report
    if write and summary["new"]:
        verify_approved_editor()
        saved = apply(data, dry_run=False)
        if saved["summary"]["entries"]["new"] != summary["new"] or saved["summary"]["entries"]["changed"] != 0:
            raise RuntimeError("Saved rows differ from approved dry-run")
        report.update({"status": "SAVED_UNVERIFIED_ENTRIES", "saved": True})
    elif write:
        report["status"] = "UNCHANGED_NO_WRITES"
    return report


def self_test():
    from discover_tospo_races import VENUE_CODES
    assert len(VENUE_CODES) == 43
    try:
        verify_approved_editor()
    except ValueError:
        pass
    else:
        if "GOOGLE_SERVICE_ACCOUNT_JSON" not in os.environ:
            raise AssertionError("Absent credential accepted")
    sample = '<a href="/list/race/example">FⅠ 静岡 初日 1R</a>'
    bad = run("2026-11-24", sample,
              loader=lambda url: "<h1>静岡 2026年11月23日 1R</h1>", max_venues=1)
    assert bad["status"] == "SOURCE_UNAVAILABLE_OR_NO_VALID_RACECARD"
    print("SELF_TEST_OK: daily auto intake bounded fail-closed and editor policy")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--apply",action="store_true")
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--max-venues",type=int,default=8)
    p.add_argument("--days",type=int,choices=(1,2),default=2)
    a=p.parse_args()
    if a.self_test:
        self_test()
        return
    if not 1 <= a.max_venues <= 12:
        p.error("max-venues must be 1..12")
    start=datetime.now(JST).date()
    index=fetch(LIST_URL)
    results=[]
    for n in range(a.days):
        day=(start+timedelta(days=n)).isoformat()
        results.append(run(day,index,max_venues=a.max_venues,write=a.apply))
    print(json.dumps({"schema":"ki-daily-auto-intake-report-v1",
                      "formalPass":False, "results":results},ensure_ascii=False))


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("DAILY_AUTO_ABORT: "+type(exc).__name__+": "+str(exc),file=sys.stderr)
        sys.exit(1)
