#!/usr/bin/env python3
"""Read-only queue of verified results without published pre-race forecasts."""
import argparse
import json
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def queue(results, lines, limit=20, offset=0, rider_feed=None):
    if not 5 <= limit <= 20 or offset < 0:
        raise ValueError("limit must be 5..20; offset must be nonnegative")
    def index(feed):
        records = feed["races"]
        out = {}
        for race in records:
            key = race.get("key") or race.get("id")
            if not key or key in out:
                raise ValueError("missing or duplicate race key")
            if race.get("id") and race.get("key") and race["id"] != race["key"]:
                raise ValueError("conflicting race key")
            out[key] = race
        return out
    result = index(results)
    line = index(lines)
    missing = [r for k,r in result.items() if k not in line]
    def priority(r):
        grade = str(r.get("grade", "")) + str(r.get("className", ""))
        a7 = int(r.get("size", 0)) == 7 and ("A級" in grade or "A3" in grade or "A1" in grade or "A2" in grade)
        midnight = "ミッドナイト" in str(r.get("meetingType", "")) + str(r.get("className", ""))
        return (not a7, not midnight, r["key"])
    missing.sort(key=priority)
    candidates = [{k:r.get(k) for k in ("key","date","track","track_code","race","size","grade","className","preRaceFormation")}
                  for r in missing[offset:offset+limit]]
    if rider_feed is not None:
        columns = rider_feed["columns"]
        fields = ("name", "prefecture", "period", "date", "track", "trackCode", "race", "number")
        if any(columns.count(field) != 1 for field in fields):
            raise ValueError("Missing or duplicate rider feed column")
        indices = {field: columns.index(field) for field in fields}
        by_key = {c["key"]: [] for c in candidates}
        for row in rider_feed["rows"]:
            if len(row) <= max(indices.values()):
                raise ValueError("Incomplete rider result row")
            item = {field: row[i] for field, i in indices.items()}
            key = f'{item["date"]}|{str(item["trackCode"]).zfill(2)}|{int(item["race"])}'
            if key in by_key:
                by_key[key].append(item)
        for candidate in candidates:
            riders = by_key[candidate["key"]]
            numbers = [int(r["number"]) for r in riders]
            complete = (candidate["size"] in (7, 9)
                        and sorted(numbers) == list(range(1, candidate["size"] + 1))
                        and all(r["track"] == candidate["track"] and r["name"]
                                and r["prefecture"] and r["period"] for r in riders))
            candidate["referenceIdentityComplete"] = bool(complete)
            candidate["referenceRiders"] = [
                {field: r[field] for field in ("number", "name", "prefecture", "period")}
                for r in sorted(riders, key=lambda r: int(r["number"]))]
    return {"results":len(result),"lines":len(line),"common":len(result.keys() & line.keys()),
            "missing":len(missing),"offset":offset,"nextOffset":offset+limit if offset+limit<len(missing) else None,
            "formalPass":False,"candidates":candidates}

def archive_candidates(archives, lines, limit):
    """Find reusable, complete pre-start observations for human/AI review."""
    published = {race["id"] for race in lines["races"]}
    candidates = []
    for archive in archives:
        if (archive["schema"] != "ki-daily-history-v1"
                or archive["verification"] != "source_sheet_unverified_do_not_treat_as_formal_PASS"):
            raise ValueError("Unexpected daily history schema")
        day = archive["date"]
        for race in archive["races"]:
            key = race["key"]
            if (key in published or race["date"] != day
                    or not re.fullmatch(re.escape(day) + r"\|[0-9]{2}\|[1-9][0-9]?", key)):
                continue
            entries = race["entries"]
            size = len(entries)
            if size not in (7, 9):
                continue
            cars = list(range(1, size + 1))
            if sorted(row["number"] for row in entries) != cars:
                continue
            observation = race.get("lineSnapshots", {}).get("preRace", {})
            by_car = observation.get("byCar", {})
            source = urlsplit(observation.get("sourceUrl") or "")
            if source.scheme != "https" or not source.hostname or set(by_car) != set(map(str, cars)):
                continue
            try:
                captured = datetime.strptime(observation["capturedAt"], "%Y-%m-%d %H:%M JST")
                starts = datetime.fromisoformat(f"{day}T{race['startTime']}")
            except (KeyError, TypeError, ValueError):
                continue
            if captured >= starts:
                continue
            groups = {by_car[str(car)] for car in cars}
            if not all(re.fullmatch(r"[1-9](?:-[1-9])*", group) for group in groups):
                continue
            members = [int(car) for group in groups for car in group.split("-")]
            consistent = all(by_car.get(car) == group for group in groups for car in group.split("-"))
            if sorted(members) != cars or not consistent:
                continue
            grade = race.get("className", "")
            priority = size == 7 and any(tag in grade for tag in ("A1", "A2", "A3", "A級"))
            candidates.append((not priority, -date.fromisoformat(day).toordinal(),
                               key, grade, observation["capturedAt"]))
    candidates.sort(key=lambda row: (row[0], row[1], row[2][:13], int(row[2].rsplit("|", 1)[1])))
    return candidates[:limit], len(candidates)


def archive_summary(limit):
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    archives = []
    for days_ago in range(3):
        path = ROOT / "daily-history" / f"{today - timedelta(days=days_ago)}.json"
        if path.is_file():
            archives.append(json.loads(path.read_text(encoding="utf-8")))
    lines = json.loads((ROOT / "verified-line-snapshots-feed-v1.json").read_text(encoding="utf-8"))
    candidates, count = archive_candidates(archives, lines, limit)
    days = "、".join(archive["date"] for archive in archives) or "なし"
    print("## 発走前ラインの照合候補")
    print(f"\n確認した日次履歴 {days}。未公開の候補 {count}R、表示 {len(candidates)}R。")
    print("全車番と取得時刻を点検した候補です。正式PASSは0Rです。")
    if candidates:
        print("\n| レースキー | 級班 | 発走前の取得時刻 |\n|---|---|---|")
        for _, _, key, grade, captured in candidates:
            print(f"| {key.replace('|', '&#124;')} | {grade.replace('|', '&#124;')} | {captured} |")


def self_test():
    rows = [{"key":f"2026-01-01|22|{n}","size":7,"grade":"A級"} for n in range(1,8)]
    r = {"races":rows}
    l = {"races":[{"id":rows[0]["key"]}]}
    q = queue(r,l,5)
    assert q["missing"] == 6 and q["common"] == 1 and len(q["candidates"]) == 5
    assert q["nextOffset"] == 5 and not q["formalPass"]
    assert len(queue(r,l,5,5)["candidates"]) == 1
    assert all(x["key"] != rows[0]["key"] for x in q["candidates"])
    try:
        queue({"races":rows+rows},l)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate key accepted")
    rows[1].update(track="前橋")
    cols = ["name","prefecture","period","date","track","trackCode","race","number"]
    reference = {"columns":cols,"rows":[["選手"+str(n),"東京","100","2026-01-01","前橋","22",2,n] for n in range(1,8)]}
    candidate = queue(r,l,5,rider_feed=reference)["candidates"][0]
    assert candidate["referenceIdentityComplete"] and len(candidate["referenceRiders"]) == 7
    reference["rows"].append(reference["rows"][0])
    assert not queue(r,l,5,rider_feed=reference)["candidates"][0]["referenceIdentityComplete"]
    day = "2026-01-01"
    race = {"date": day, "key": f"{day}|22|1", "className": "A3", "startTime": "18:00",
            "entries": [{"number": n} for n in range(1, 8)]}
    observation = {"sourceUrl": "https://example.org/race", "capturedAt": f"{day} 17:59 JST",
                   "byCar": {str(n): str(n) for n in range(1, 8)}}
    race["lineSnapshots"] = {"preRace": observation}
    archive = {"schema": "ki-daily-history-v1", "date": day, "races": [race],
               "verification": "source_sheet_unverified_do_not_treat_as_formal_PASS"}
    assert archive_candidates([archive], {"races": []}, 5)[1] == 1
    assert archive_candidates([archive], l, 5)[1] == 0
    observation["capturedAt"] = f"{day} 18:00 JST"
    assert archive_candidates([archive], {"races": []}, 5)[1] == 0
    observation["capturedAt"] = f"{day} 17:59 JST"
    observation["byCar"]["1"] = "1-2"
    assert archive_candidates([archive], {"races": []}, 5)[1] == 0
    print("SELF_TEST_OK: missing-line queue, paging, duplicate rejection and archive candidate checks")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit",type=int,default=20)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--daily-archive-summary", action="store_true")
    args=p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.daily_archive_summary:
        if not 5 <= args.limit <= 20:
            p.error("--limit must be 5..20")
        archive_summary(args.limit)
        return
    def load(name):
        return json.loads((ROOT/name).read_text(encoding="utf-8"))
    print(json.dumps(queue(load("verified-results-feed-v1.json"),
                           load("verified-line-snapshots-feed-v1.json"),
                           args.limit,args.offset,load("verified-rider-results-feed-v1.json")),ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
