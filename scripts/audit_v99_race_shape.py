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
                or not str(row[4]).isdigit() or not str(row[7]).isdigit()
                or not 1 <= int(row[2]) <= 99 or not 1 <= int(row[4]) <= 12
                or not 1 <= int(row[7]) <= 9):
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



def meeting_coverage(v99_rows, v100_rows, cancelled_rows):
    """Read-only cross-ledger checks; never infer a missing race from V99 alone."""
    if not v100_rows or v100_rows[0][:3] != ["開催キー", "開催日", "競輪場"]:
        raise ValueError("V100 source header mismatch")
    if not cancelled_rows or cancelled_rows[0][:2] != ["レースキー", "開催日"]:
        raise ValueError("Cancelled-race source header mismatch")
    by_meeting = defaultdict(set)
    for row in v99_rows[1:]:
        if len(row) < 8 or not row[0] or not str(row[2]).isdigit() or not str(row[4]).isdigit():
            continue
        key = f"{row[0]}|{int(row[2]):02d}"
        by_meeting[key].add(int(row[4]))
    cancelled = set()
    for row in cancelled_rows[1:]:
        if len(row) >= 7 and str(row[6]).strip() == "中止":
            cancelled.add(str(row[0]).strip())
    v100_only = []
    missing_candidates = []
    cancelled_covered = 0
    reviewed = 0
    for row in v100_rows[1:]:
        if len(row) < 9 or not str(row[0]).strip():
            continue
        key = str(row[0]).strip()
        if key not in by_meeting:
            # V100 summarizes V95-V99, not just the V99 sheet.
            v100_only.append(key)
            continue
        last = str(row[8]).strip()
        if not last.isdigit() or not 1 <= int(last) <= 12:
            missing_candidates.append({"meetingKey": key, "status": "INVALID_V100_RACE_LIMIT"})
            continue
        reviewed += 1
        for race in range(1, int(last) + 1):
            if race in by_meeting[key]:
                continue
            if f"{key}|{race}" in cancelled:
                cancelled_covered += 1
            else:
                missing_candidates.append({"meetingKey": key, "race": race,
                                           "status": "REVIEW_SOURCE_MEETING_AND_CANCELLATION"})
    return {
        "readOnly": True, "formalPass": False,
        "v100MeetingsNotInV99": len(v100_only),
        "v100OnlyMeetingSample": v100_only[:10],
        "v100MeetingsComparedToV99": reviewed,
        "cancelledRacesExplainingGaps": cancelled_covered,
        "unexplainedRaceNumberGapCount": len(missing_candidates),
        "unexplainedRaceNumberGapSample": missing_candidates[:20],
        "limitation": ("V100 covers older V95-V98 sources as well as V99. "
                       "A V100-only meeting is not proof of a missing race.")
    }



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
    assert audit(data + [row("3", 10)])["invalidKeyRows"] == 1
    v100 = [["開催キー", "開催日", "競輪場", "場コード", "グレード",
             "通常結果R", "中止R", "選手行", "最終保存R"],
            ["2026-11-01|24", "2026-11-01", "試験場", "24", "F2", "2", "1", "13", "3"],
            ["2026-10-01|22", "2026-10-01", "旧テスト場", "22", "F2", "1", "0", "7", "1"]]
    cancelled = [["レースキー", "開催日"], ["2026-11-01|24|3", "2026-11-01",
                 "試験場", "24", "3", "F2", "中止"]]
    scope = meeting_coverage([HEADER] + data[1:], v100, cancelled)
    assert scope["v100MeetingsNotInV99"] == 1
    assert scope["cancelledRacesExplainingGaps"] == 1
    assert scope["unexplainedRaceNumberGapCount"] == 0
    assert meeting_coverage(data, v100, [cancelled[0]])["unexplainedRaceNumberGapCount"] == 1
    assert scope["formalPass"] is False
    print("SELF_TEST_OK: V99 read-only shape and cross-ledger coverage checks")


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
