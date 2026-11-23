#!/usr/bin/env python3
"""Read-only V99 race-row shape triage. Row counts never grant PASS."""
import argparse
import json
from collections import Counter, defaultdict


HEADER = ["開催日", "競輪場", "場コード", "グレード", "R", "レース級",
          "着順原文", "車番", "選手名"]


def audit(rows, sample_limit=20):
    if not rows or rows[0][:len(HEADER)] != HEADER:
        raise ValueError("V99 source header mismatch")
    races = defaultdict(list)
    invalid_rows = 0
    for row in rows[1:]:
        if not row or not str(row[0]).strip():
            continue
        if (len(row) < 8 or not str(row[2]).isdigit()
                or not str(row[4]).isdigit() or not str(row[7]).isdigit()):
            invalid_rows += 1
            continue
        key = f"{row[0]}|{int(row[2]):02d}|{int(row[4])}"
        races[key].append(row)
    histogram = Counter()
    review = []
    duplicates = []
    numbered_gaps = 0
    for key, group in sorted(races.items()):
        n = len(group)
        histogram[str(n)] += 1
        cars = [int(row[7]) for row in group]
        if len(set(cars)) != len(cars):
            duplicates.append(key)
        # Gaps are only provisional: a starting card or official absence
        # record must establish whether a result row is truly missing.
        numbered = set(cars)
        gaps = sorted(set(range(1, max(numbered) + 1)) - numbered)
        if n not in (7, 9) or gaps or len(cars) != len(numbered):
            if gaps:
                numbered_gaps += 1
            review.append({"raceKey": key, "storedRows": n,
                           "venue": str(group[0][1]), "raceClass": str(group[0][5]),
                           "storedCars": sorted(cars),
                           "numberingGaps": gaps,
                           "reason": ("REVIEW_GAP_WITH_ENTRY_AND_EXCEPTIONS" if gaps
                                      else "VERIFY_STARTING_CARD_AND_EXCEPTIONS")})
    return {"schema": "ki-v99-shape-audit-v1", "readOnly": True,
            "formalPass": False,
            "storedRiderRows": sum(len(group) for group in races.values()),
            "storedRaces": len(races),
            "storedRowCounts": dict(sorted(histogram.items(), key=lambda kv: int(kv[0]))),
            "outOf7Or9Races": sum(count for size, count in histogram.items()
                                   if size not in ("7", "9")),
            "numberingGapRaceCount": numbered_gaps,
            "reviewCount": len(review), "invalidKeyRows": invalid_rows,
            "duplicateCarRaceCount": len(duplicates),
            "reviewSample": review[:sample_limit],
            "limitations": ("Row count alone cannot prove incomplete results. "
                            "Check the complete starting field and cancellations.")}


def live_rows():
    from upsert_daily_sheets import SHEET_ID, remote_client
    session, token = remote_client()
    base = "https://sheets.googleapis.com/v4/spreadsheets/" + SHEET_ID + "/values/"
    all_rows = []
    for lo in range(1, 10001, 1000):
        hi = min(lo + 999, 10000)
        range_id = f"'V99選手結果蓄積'!A{lo}:R{hi}"
        response = session.get(base + range_id,
                               headers={"Authorization": "Bearer " + token},
                               timeout=40)
        response.raise_for_status()
        values = response.json().get("values", [])
        all_rows.extend(values)
        if len(values) < hi - lo + 1:
            break
    return all_rows


def self_test():
    def row(race, car):
        return ["2026-11-01", "試験場", "24", "F2", race, "A",
                str(car), str(car), "架空選手"]
    data = [HEADER] + [row("1", n) for n in range(1, 8)] + [
        row("2", n) for n in range(1, 7)]
    report = audit(data)
    assert report["storedRaces"] == 2 and report["outOf7Or9Races"] == 1
    assert report["storedRowCounts"] == {"6": 1, "7": 1}
    assert report["reviewSample"][0]["raceKey"] == "2026-11-01|24|2"
    assert report["reviewSample"][0]["numberingGaps"] == []
    assert report["reviewSample"][0]["storedCars"] == [1, 2, 3, 4, 5, 6]
    assert report["numberingGapRaceCount"] == 0
    data[-1][7] = "7"
    review_gapped = audit(data)
    assert review_gapped["numberingGapRaceCount"] == 1
    assert review_gapped["reviewSample"][0]["numberingGaps"] == [6]
    data[-1][7] = "6"
    assert report["formalPass"] is False
    data[-1][7] = "5"
    assert audit(data)["duplicateCarRaceCount"] == 1
    print("SELF_TEST_OK: V99 read-only shape audit and duplicate detection")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--live", action="store_true", help="Google V99 read-only, no writes")
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if not args.live:
        p.error("Specify --self-test or --live")
    print(json.dumps(audit(live_rows()), ensure_ascii=False))


if __name__ == "__main__":
    main()
