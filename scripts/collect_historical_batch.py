#!/usr/bin/env python3
"""Bounded historical result collection into *candidate* JSON only.

Reads a small explicit JSON worklist. Reuses collect_historical_pair, keeps a
deterministic candidate file per race, skips an unchanged verified candidate
on replay, and writes a summary. No Sheet, official feed or PASS writes.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

from collect_historical_pair import collect, collect_auto
from result_hold_diagnostics import classify_result_hold, review_route
from compare_race_results import compare

MAX_BATCH = 10
ALLOWED_CLASSES = {"A3", "A1A2", "A1", "A2", "S", "S1", "S2", "L1"}


def identity(row):
    if not isinstance(row, dict):
        raise ValueError("Each race must be a JSON object")
    day, code, number = row.get("date"), str(row.get("trackCode", "")), row.get("race")
    if not isinstance(day, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day):
        raise ValueError("Invalid race date")
    date.fromisoformat(day)
    if not code.isdigit() or not 1 <= int(code) <= 99:
        raise ValueError("Invalid track code")
    if type(number) is not int or not 1 <= number <= 12:
        raise ValueError("Invalid race number")
    track, cls, cars = row.get("track"), row.get("className"), row.get("expectedCars")
    if not isinstance(track, str) or not track.strip() or cls not in ALLOWED_CLASSES:
        raise ValueError("Invalid track or class")
    if type(cars) is not int or cars not in (7, 9):
        raise ValueError("Expected cars must be 7 or 9")
    for prop in ("leftUrl", "rightUrl"):
        if prop in row and (not isinstance(row[prop], str) or not row[prop].startswith("https://")):
            raise ValueError("Invalid optional source URL")
    return f"{day}|{int(code):02d}|{number}"


def digest_spec(row):
    normalized = {
        "date": row["date"], "trackCode": f'{int(row["trackCode"]):02d}',
        "track": row["track"], "race": row["race"],
        "className": row["className"], "expectedCars": row["expectedCars"],
        "leftUrl": row.get("leftUrl", ""), "rightUrl": row.get("rightUrl", "")
    }
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def store(path, object_value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".partial")
    pending.write_text(json.dumps(object_value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def run(plan, output):
    if not isinstance(plan, dict) or not isinstance(plan.get("races"), list):
        raise ValueError("Input must contain races array")
    races = plan["races"]
    if not 1 <= len(races) <= MAX_BATCH:
        raise ValueError("Batch size must be 1 to 10")
    keys = [identity(row) for row in races]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate race key in batch: no writes performed")
    output = Path(output)
    if output.resolve() == Path("/"):
        raise ValueError("Invalid output directory")
    processed = []
    for row, key in zip(races, keys):
        spec_sha = digest_spec(row)
        filename = key.replace("|", "_") + ".json"
        file = output / filename
        if file.exists():
            try:
                existing = json.loads(file.read_text(encoding="utf-8"))
                meta = existing.get("batchMeta", {})
                result = existing.get("comparison", {})
                if (meta.get("specHash") == spec_sha and result.get("raceKey") == key
                        and result.get("formalPass") is False
                        and result.get("carCount") == row["expectedCars"]
                        and isinstance(existing.get("observations"), list)
                        and len(existing["observations"]) == 2):
                    verified = compare({"observations": existing["observations"]})
                    # Recompute the result from the stored rows; do not trust a
                    # claimed previous comparison or an attacker-edited summary.
                    if verified == result:
                        observed_race = existing["observations"][0]["race"]
                        if (observed_race["track"] == row["track"]
                                and observed_race["className"] == row["className"]):
                            processed.append({"raceKey": key, "status": "SKIPPED_EXISTING_CANDIDATE"})
                            continue
            except (OSError, ValueError, AttributeError):
                pass
            processed.append({"raceKey": key, "status": "EXISTING_FILE_CONFLICT_REVIEW"})
            continue
        try:
            args = (row["date"], str(row["trackCode"]), row["track"],
                    row["race"], row["className"], row["expectedCars"])
            # User-specified historic URLs preserve the original pinned pair.
            # Otherwise use the same source-neutral pool as daily result intake.
            if row.get("leftUrl") or row.get("rightUrl"):
                data = collect(*args, row.get("leftUrl"), row.get("rightUrl"))
            else:
                data = collect_auto(*args)
            data["batchMeta"] = {"schema": "ki-historical-candidate-batch-v1", "specHash": spec_sha}
            if data["comparison"]["raceKey"] != key or data["comparison"]["formalPass"] is not False:
                raise ValueError("Candidate comparison identity or PASS boundary mismatch")
            store(file, data)
            source_id = data["observations"][1]["sourceId"]
            processed.append({"raceKey": key, "status": data["comparison"]["status"],
                              "disagreements": len(data["comparison"]["disagreements"]),
                              "secondSourceId": source_id,
                              "alternateSourceUsed": source_id == "lotoplace-day-results"})
        except Exception as exc:
            # Do not record raw page or service credential contents in the summary.
            processed.append({"raceKey": key, "status": "SOURCE_ERROR",
                              "errorType": type(exc).__name__,
                              "reasonCode": classify_result_hold(exc, "COLLECT_COMPARE"),
                              "reviewRoute": review_route(classify_result_hold(exc, "COLLECT_COMPARE"))})
    summary = {"schema": "ki-batch-summary-v1", "formalPass": False,
               "requested": len(races), "results": processed}
    store(output / "batch-summary.json", summary)
    return summary


def self_test():
    demo = {"date": "2026-09-10", "trackCode": "27", "track": "京王閣",
            "race": 2, "className": "A3", "expectedCars": 7}
    assert identity(demo) == "2026-09-10|27|2"
    try:
        identity({**demo, "expectedCars": 6})
    except ValueError:
        pass
    else:
        raise AssertionError("Six-car plan accepted")
    try:
        run({"races": [demo, dict(demo)]}, "/tmp/ki-batch-invalid-dup")
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate key accepted")
    assert digest_spec(demo) == digest_spec(dict(demo))
    assert classify_result_hold(ValueError("Rider class conflicts with requested race class"), "COLLECT_COMPARE") == "SOURCE_RIDER_CLASS_MISMATCH"
    assert review_route("SOURCE_RIDER_CLASS_MISMATCH") == "RIDER_OR_CLASS_EVIDENCE_REVIEW"
    from unittest.mock import patch
    from tempfile import TemporaryDirectory
    rows = [{"number": i, "name": f"選手{i}", "prefecture": "京都",
             "period": "93", "finish": str(i), "method": "", "exception": ""}
            for i in range(1, 8)]
    def make_obs(url, sid):
        return {"sourceUrl": url, "sourceId": sid,
                "race": dict(demo), "results": [dict(r) for r in rows]}
    a = make_obs("https://one.example/r", "a")
    b = make_obs("https://two.example/r", "b")
    valid = {"observations": [a, b],
             "comparison": compare({"observations": [a, b]})}
    with TemporaryDirectory() as directory:
        with patch.object(sys.modules[__name__], "collect_auto", return_value=valid) as pooled:
            first = run({"races": [demo]}, directory)
            pooled.assert_called_once_with(demo["date"], demo["trackCode"],
                                           demo["track"], demo["race"],
                                           demo["className"], demo["expectedCars"])
            assert first["results"][0]["status"] == "SOURCE_CONTENT_MATCH_INDEPENDENCE_PENDING"
            assert first["results"][0]["secondSourceId"] == "b"
            assert first["results"][0]["alternateSourceUsed"] is False
        with patch.object(sys.modules[__name__], "collect_auto", side_effect=AssertionError("unnecessary fetch")):
            repeat = run({"races": [demo]}, directory)
            assert repeat["results"][0]["status"] == "SKIPPED_EXISTING_CANDIDATE"
        p = Path(directory) / "2026-09-10_27_2.json"
        candidate = json.loads(p.read_text(encoding="utf-8"))
        candidate["observations"][0]["results"][0]["finish"] = "2"
        store(p, candidate)
        with patch.object(sys.modules[__name__], "collect_auto", side_effect=AssertionError("must not overwrite")):
            corrupted = run({"races": [demo]}, directory)
            assert corrupted["results"][0]["status"] == "EXISTING_FILE_CONFLICT_REVIEW"

    # A pinned publication pair must never be silently replaced by a pool.
    with TemporaryDirectory() as directory:
        pinned = {**demo, "leftUrl": "https://one.example/r",
                  "rightUrl": "https://two.example/r"}
        with (patch.object(sys.modules[__name__], "collect", return_value=valid) as fixed,
              patch.object(sys.modules[__name__], "collect_auto",
                           side_effect=AssertionError("unexpected source pool"))):
            run({"races": [pinned]}, directory)
            fixed.assert_called_once()
    print("SELF_TEST_OK: bounded historical candidate plan, source-neutral fallback, pinned pair and duplicates")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan")
    p.add_argument("--out-dir")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if not args.plan or not args.out_dir:
        p.error("--plan and --out-dir required")
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    result = run(plan, args.out_dir)
    print(json.dumps(result, ensure_ascii=False))
    if any(row["status"] in ("SOURCE_ERROR", "EXISTING_FILE_CONFLICT_REVIEW")
           for row in result["results"]):
        # We have a usable partial batch artifact but never call it full success.
        sys.exit(2)


if __name__ == "__main__":
    main()
