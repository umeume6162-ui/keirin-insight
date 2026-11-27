"""Audit saved keirin prediction candidates against a verified finishing order."""
import argparse
import json
from pathlib import Path
import re

from race_card_score import prediction_acquisition_check, sheet_capture_time


def audit_outcome(prediction, result):
    race_key = prediction["レースID"]
    report = {"prediction_id": prediction["予想ID"], "race_id": race_key}
    if race_key != result["race_id"] or not re.fullmatch(r"\d{4}-\d{2}-\d{2}\|\d{2}\|(?:[1-9]|1[0-2])", race_key):
        return dict(report, state="HOLD_RACE_MISMATCH")
    times = [sheet_capture_time(v) for v in (
        prediction["使用データ時点(JST)"], prediction["予想記録日時(JST)"], result["start_at"]
    )]
    observed, recorded, start = times
    time_state = prediction_acquisition_check(observed, observed, recorded, start)
    if time_state != "TIME_PASS" or start[:10] != race_key[:10]:
        return dict(report, state=time_state if time_state != "TIME_PASS" else "HOLD_RACE_MISMATCH")

    if result.get("confirmed") is not True:
        return dict(report, state="HOLD_RESULT_UNCONFIRMED")
    size = str(prediction["車立て"])
    order = result.get("order", [])
    if (size not in ("7", "9") or not isinstance(order, list) or len(order) != int(size)
            or any(type(number) is not int for number in order)
            or sorted(order) != list(range(1, int(size) + 1))):
        return dict(report, state="HOLD_INCOMPLETE_ORDER")
    actual = order[:3]
    candidate_text = prediction.get("三連単候補") or ""
    if not candidate_text.strip():
        return dict(report, state="NO_SAVED_CANDIDATES", actual=actual)
    picks = []
    for pick in re.split(r"[,、\n]", candidate_text):
        cleaned = pick.strip()
        if not re.fullmatch(r"[1-9]-[1-9]-[1-9]", cleaned):
            return dict(report, state="HOLD_CANDIDATE_FORMAT", actual=actual)
        numbers = list(map(int, cleaned.split("-")))
        if len(set(numbers)) != 3 or any(n > int(size) for n in numbers):
            return dict(report, state="HOLD_CANDIDATE_FORMAT", actual=actual)
        picks.append(numbers)
    return dict(report, state="CHECKED", actual=actual, candidate_count=len(picks),
                exact_order=actual in picks, winning_car_listed=any(x[0] == actual[0] for x in picks))


def audit_batch(snapshots, existing):
    """Plan outcome reviews while preserving existing verification rows."""
    from collections import Counter

    verified = {}
    for row in existing:
        pred_id = row.get("予想ID")
        race_id = row.get("レースID")
        if pred_id and race_id:
            verified.setdefault(pred_id, set()).add(race_id)
    counts, reports, seen = Counter(), [], set()
    for snapshot in snapshots:
        prediction = snapshot["prediction"]
        pred_id, race_id = prediction["予想ID"], prediction["レースID"]
        if not pred_id or pred_id in seen:
            raise ValueError("Missing or duplicate prediction ID")
        seen.add(pred_id)
        known = verified.get(pred_id)
        if known:
            state = "ALREADY_REVIEWED" if known == {race_id} else "HOLD_REVIEW_KEY_CONFLICT"
            report = {"prediction_id": pred_id, "race_id": race_id, "state": state}
        else:
            report = audit_outcome(prediction, snapshot["result"])
        counts[report["state"]] += 1
        reports.append(report)
    return {"counts": dict(counts), "reports": reports}


def audit_ledger_export(data):
    """Join raw prediction and review rows to the formal public result feeds."""
    from collections import defaultdict

    def table(rows, required):
        if not rows or any(rows[0].count(name) != 1 for name in required):
            raise ValueError("Unexpected ledger headers")
        return [dict(zip(rows[0], row)) for row in rows[1:] if any(row)]

    predictions = table(data["prediction_values"], (
        "予想ID", "レースID", "車立て", "使用データ時点(JST)", "予想記録日時(JST)", "三連単候補"
    ))
    existing = table(data["review_values"], ("予想ID", "レースID"))
    if (data["results"].get("schema") != "ki-public-results-index-v1"
            or data["riders"].get("schema") != "ki-rider-results-v1"):
        raise ValueError("Expected the formal result and rider result feeds")
    index = {}
    for race in data["results"]["races"]:
        key = race["key"]
        if key in index:
            raise ValueError("Duplicate formal result key")
        index[key] = race
    by_race = defaultdict(list)
    columns = data["riders"]["columns"]
    required = ("date", "trackCode", "race", "number", "finishRaw")
    if any(columns.count(name) != 1 for name in required):
        raise ValueError("Unexpected rider result headers")
    for row in data["riders"]["rows"]:
        item = dict(zip(columns, row))
        by_race[f"{item['date']}|{item['trackCode']}|{item['race']}"].append(item)

    snapshots = []
    legacy = 0
    for row in predictions:
        key = row.get("レースID") or ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\|\d{2}\|(?:[1-9]|1[0-2])", key):
            legacy += 1
            continue
        official = index.get(key, {})
        finish = {str(r["finishRaw"]): r["number"] for r in by_race[key]}
        size = str(row.get("車立て"))
        confirmed = (official.get("officialVerification", {}).get("status") == "verified"
                     and str(official.get("size")) == size)
        places = [str(n) for n in range(1, int(size) + 1)] if size in ("7", "9") else []
        order = []
        if len(by_race[key]) == len(places) and set(finish) == set(places):
            order = [finish[place] for place in places]
        snapshots.append({"prediction": row, "result": {
            "race_id": key, "start_at": data["starts"].get(key), "confirmed": confirmed, "order": order,
        }})
    report = audit_batch(snapshots, existing)
    report["legacy_records_skipped"] = legacy
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    if "prediction_values" in data:
        report = audit_ledger_export(data)
    elif "snapshots" in data:
        report = audit_batch(data["snapshots"], data.get("existing", []))
    else:
        report = audit_outcome(data["prediction"], data["result"])
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
