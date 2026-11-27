"""Read-only comparison of starting line roles in verified A1/A2 3-2-2 races."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import unicodedata


ROLES = ("three_rider_leader", "three_rider_second", "three_rider_third",
         "two_rider_leader", "two_rider_second")


def identity(name, prefecture, period):
    return tuple("".join(unicodedata.normalize("NFKC", str(value)).split())
                 for value in (name, prefecture, period))


def summarize(results, lines, riders):
    """Exclude races without a complete identity match or unique top three."""
    if not all(isinstance(feed, dict) for feed in (results, lines, riders)):
        raise ValueError("Expected three feed objects")
    line_by_key = {}
    for line in lines["races"]:
        if line["key"] in line_by_key:
            raise ValueError("Duplicate line race key")
        line_by_key[line["key"]] = line
    rider_by_key = defaultdict(list)
    for row in riders["rows"]:
        rider_by_key[f"{row[3]}|{row[5]}|{row[6]}"].append(row)

    counters = defaultdict(lambda: {role: Counter(runners=0, wins=0, top_three=0) for role in ROLES})
    included, excluded = set(), Counter()
    seen = set()
    for race in results["races"]:
        key = race["key"]
        if key in seen:
            raise ValueError("Duplicate result race key")
        seen.add(key)
        line = line_by_key.get(key)
        if race.get("grade") != "A1/A2" or race.get("size") != 7 or not line:
            continue
        groups = line.get("forecastGroups") or []
        if line.get("lineMode") in ("no_line", "contested") or sorted(map(len, groups)) != [2, 2, 3]:
            continue
        rows = rider_by_key[key]
        number_to_row = {row[8]: row for row in rows}
        forecast = {row["number"]: identity(row["name"], row["prefecture"], row["period"])
                    for row in line.get("riders", [])}
        numbers = set(range(1, 8))
        if (len(rows) != 7 or len(line.get("riders", [])) != 7 or set(forecast) != numbers
                or set(number_to_row) != numbers or sorted(n for group in groups for n in group) != sorted(numbers)
                or any(forecast[n] != identity(*number_to_row[n][:3]) for n in numbers)):
            excluded["identity_or_roster"] += 1
            continue
        if any(str(row[7]) not in "1234567" or len(str(row[7])) != 1 for row in rows):
            excluded["non_numeric_finish"] += 1
            continue
        rank = {n: int(row[7]) for n, row in number_to_row.items()}
        if sorted(place for place in rank.values() if place <= 3) != [1, 2, 3]:
            excluded["ambiguous_top_three"] += 1
            continue
        included.add(key)
        for group in groups:
            roles = ROLES[:3] if len(group) == 3 else ROLES[3:]
            for role, number in zip(roles, group):
                for bucket in ("all", race["date"][:7]):
                    count = counters[bucket][role]
                    count["runners"] += 1
                    count["wins"] += rank[number] == 1
                    count["top_three"] += rank[number] <= 3
    return {"races": len(included), "excluded": dict(excluded), "roles": dict(counters)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("."))
    args = parser.parse_args()
    names = ("verified-results-feed-v1.json", "verified-line-snapshots-feed-v1.json",
             "verified-rider-results-feed-v1.json")
    data = [json.loads((args.directory / name).read_text(encoding="utf-8")) for name in names]
    print(json.dumps(summarize(*data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
