#!/usr/bin/env python3
"""Read-only queue of verified results without published pre-race forecasts."""
import argparse
import json
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
    print("SELF_TEST_OK: missing-line queue, paging and duplicate rejection")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit",type=int,default=20)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    if args.self_test:
        self_test()
        return
    def load(name):
        return json.loads((ROOT/name).read_text(encoding="utf-8"))
    print(json.dumps(queue(load("verified-results-feed-v1.json"),
                           load("verified-line-snapshots-feed-v1.json"),
                           args.limit,args.offset,load("verified-rider-results-feed-v1.json")),ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
