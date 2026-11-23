#!/usr/bin/env python3
"""Read-only, conservative netkeirin result HTML adapter for any historical date.

Produces *one source observation* for compare_race_results.py, never formal PASS
or Google writes. The race identity comes from the page, not the input alone.
Reject ambiguous/incomplete 7/9 rider results, unknown statuses, and bad provenance.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

EXCEPTIONS = {
    "失": "失格", "失格": "失格",
    "欠": "欠車", "欠車": "欠車",
    "取消": "取消", "取": "取消",
    "落": "落車棄権", "落車": "落車棄権", "落車棄権": "落車棄権",
    "棄": "棄権", "棄権": "棄権",
    "途中棄権": "途中棄権",
}


def norm(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def compact(value):
    return re.sub(r"\s+", "", norm(value))


def validate_url(url, event_date, code, race):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != "keirin.netkeiba.com" or parts.path != "/race/result/":
        raise ValueError("Only HTTPS netkeirin /race/result/ URL is supported")
    q = parse_qs(parts.query)
    expected_id = event_date.replace("-", "") + code.zfill(2) + str(race).zfill(2)
    if q.get("race_id") != [expected_id]:
        raise ValueError("Result URL race_id differs from requested date/track/race")
    return url


def grade_matches(source_grade, expected_class):
    from_source = compact(source_grade)
    target = compact(expected_class)
    accepted = {
        "A3": {"A3"}, "A1A2": {"A1", "A2"},
        "S": {"S1", "S2"}, "L1": {"L1"},
        "A1": {"A1", "A2"}, "A2": {"A1", "A2"}, "S1": {"S1", "S2"}, "S2": {"S1", "S2"}
    }
    # A1/A2 競走 can contain both rider grades even when the sheet label is A1 or A2.
    # S1/S2 races also mix rider grades. Keep A, S and L groups separate;
    # never relax rider identity or race keys.
    if target not in accepted:
        raise ValueError("Unsupported race class for source verification")
    return from_source in accepted[target]


def extract(html, event_date, code, track, race, class_name, expected_cars, url):
    date.fromisoformat(event_date)
    if expected_cars not in (7, 9) or not 1 <= race <= 12 or not 1 <= int(code) <= 99:
        raise ValueError("Invalid race metadata")
    validate_url(url, event_date, code, race)
    soup = BeautifulSoup(html, "html.parser")
    heading = " ".join(norm(x.get_text(" ", strip=True)) for x in soup.select("title,h1"))
    # Race cards can mention other races in navigation. Verify the event in a heading.
    if track not in heading or not (
        event_date in heading or
        re.search(rf"{int(event_date[:4])}年\s*0?{int(event_date[5:7])}月\s*0?{int(event_date[8:])}日", heading)
    ):
        raise ValueError("Race date/venue not found in source heading")
    if not re.search(rf"(?<!\d){race}\s*R(?!\d)", heading):
        raise ValueError("Requested R not proven in page heading")
    matched_tables = []
    for table in soup.select("table"):
        for tr in table.select("tr"):
            names = [compact(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"], recursive=False)]
            headers = {}
            for wanted, aliases in {
                "finish": ("着", "着順"), "number": ("車番",),
                "rider": ("選手名",), "method": ("決", "決まり手")
            }.items():
                indexes = [i for i, x in enumerate(names) if x in aliases]
                if len(indexes) == 1:
                    headers[wanted] = indexes[0]
            if len(headers) < 3 or not all(k in headers for k in ("finish", "number", "rider")):
                continue
            found = []
            for row in tr.find_next_siblings("tr"):
                cells = row.find_all(["th", "td"], recursive=False)
                if len(cells) <= max(headers.values()):
                    continue
                car = compact(cells[headers["number"]].get_text(" ", strip=True))
                if not car.isdigit() or not 1 <= int(car) <= expected_cars:
                    continue
                finished = compact(cells[headers["finish"]].get_text(" ", strip=True))
                rank = re.fullmatch(r"([1-9])着?", finished)
                ex = EXCEPTIONS.get(finished)
                if rank and 1 <= int(rank[1]) <= expected_cars:
                    finish = str(int(rank[1]))
                    exception = ""
                elif ex:
                    finish = exception = ex
                else:
                    raise ValueError("Unknown finish/exception state")
                rider_text = norm(cells[headers["rider"]].get_text(" ", strip=True))
                # Typical example: 伊藤司 福島 48歳 83期 A3
                match = re.match(
                    r"^(.+?)\s+([^\s\d/]+)\s+\d{1,2}歳\s+(\d{1,3})期\s+([ASL][123])(?:\s|$)",
                    rider_text
                )
                if not match:
                    raise ValueError("Name/prefecture/period not fully visible for car " + car)
                name, prefecture, period, source_grade = match.groups()
                if not grade_matches(source_grade, class_name):
                    raise ValueError("Rider class conflicts with requested race class")
                method = (compact(cells[headers["method"]].get_text(" ", strip=True))
                          if "method" in headers else "")
                found.append({
                    "number": int(car), "name": name, "prefecture": prefecture,
                    "period": period, "finish": finish, "method": method,
                    "exception": exception
                })
            if len(found) == expected_cars and sorted(x["number"] for x in found) == list(range(1, expected_cars + 1)):
                matched_tables.append(sorted(found, key=lambda x: x["number"]))
    if len(matched_tables) != 1:
        raise ValueError("Exactly one complete 7/9-car result table required")
    return {
        "sourceUrl": url, "sourceId": "netkeirin-result",
        "race": {"date": event_date, "trackCode": str(code).zfill(2),
                 "track": track, "race": race, "className": class_name,
                 "expectedCars": expected_cars},
        "results": matched_tables[0],
        "provenance": "HTML page observation; not independent PASS"
    }


def fetch(url):
    import requests
    from urllib.robotparser import RobotFileParser
    agent = "KEIRIN-INSIGHT-Research/1.0 (one public result read-only)"
    robots = requests.get("https://keirin.netkeiba.com/robots.txt",
                          headers={"User-Agent": agent}, timeout=15)
    if robots.status_code == 200:
        parser = RobotFileParser()
        parser.parse(robots.text.splitlines())
        if not parser.can_fetch(agent, url):
            raise ValueError("Robots rules prohibit this page")
    elif robots.status_code not in (404, 410):
        raise ValueError("Unable to confirm robots access; no fetch")
    response = requests.get(url, headers={"User-Agent": agent}, timeout=20)
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise ValueError("Source HTML too large")
    return response.text


def self_test():
    url = "https://keirin.netkeiba.com/race/result/?race_id=202609102702"
    headings = "<title>京王閣 2026年09月10日 2R 結果</title>"
    header = "<tr><th>着</th><th>枠番</th><th>車番</th><th>選手名</th><th>着差</th><th>上り</th><th>決</th></tr>"
    rows = "".join(
        f"<tr><td>{n}着</td><td>1</td><td>{n}</td><td>テスト選手{n} 福島 48歳 83期 A3</td>"
        f"<td>1/2車身</td><td>12.0</td><td>{'差' if n==1 else ''}</td></tr>"
        for n in range(1, 8)
    )
    html = "<html><head>" + headings + "</head><body><table>" + header + rows + "</table></body></html>"
    args = ("2026-09-10", "27", "京王閣", 2, "A3", 7, url)
    r = extract(html, *args)
    assert len(r["results"]) == 7 and r["results"][0]["finish"] == "1"
    mixed = html.replace("83期 A3", "83期 A1").replace(
        "テスト選手2 福島 48歳 83期 A1", "テスト選手2 福島 48歳 83期 A2")
    observed_mixed = extract(mixed, "2026-09-10", "27", "京王閣", 2,
                             "A2", 7, url)
    assert len(observed_mixed["results"]) == 7
    mixed_s = html.replace("83期 A3", "83期 S1").replace(
        "テスト選手2 福島 48歳 83期 S1", "テスト選手2 福島 48歳 83期 S2")
    assert len(extract(mixed_s, "2026-09-10", "27", "京王閣", 2, "S2", 7, url)["results"]) == 7
    assert grade_matches("A1", "A2") and grade_matches("A2", "A1")
    assert grade_matches("S1", "S2") and grade_matches("S2", "S1")
    assert not grade_matches("A1", "S2") and not grade_matches("A3", "S1")
    assert grade_matches("A3", "A3") and not grade_matches("A3", "A2")
    assert not grade_matches("S1", "A1") and not grade_matches("L1", "A2")
    try:
        extract(html, "2026-09-10", "27", "京王閣", 2, "S", 7, url)
    except ValueError:
        pass
    else:
        raise AssertionError("Wrong source class accepted")

    for bad in (html.replace("<td>7</td>", "<td>6</td>"),
                html.replace(" 2R", " 3R")):
        try:
            extract(bad, *args)
        except ValueError:
            pass
        else:
            raise AssertionError("Inconsistent source table accepted")
    nav_bait = html.replace(" 2R 結果", " 3R 結果").replace(
        "</body>", "<h2>京王閣 2026年09月10日 2R</h2></body>"
    )
    try:
        extract(nav_bait, *args)
    except ValueError:
        pass
    else:
        raise AssertionError("Navigation heading overrode incorrect title")
    print("SELF_TEST_OK: historical netkeirin result adapter, complete field and R guards")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date")
    p.add_argument("--track-code")
    p.add_argument("--track")
    p.add_argument("--race", type=int)
    p.add_argument("--class-name")
    p.add_argument("--expected-cars", type=int)
    p.add_argument("--url")
    p.add_argument("--html-fixture")
    p.add_argument("--out", default="/tmp/ki-history-result-source.json")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    if not all([a.date, a.track_code, a.track, a.race, a.class_name, a.expected_cars, a.url]):
        p.error("date, track-code, track, race, class-name, expected-cars, url required")
    validate_url(a.url, a.date, a.track_code, a.race)
    html = Path(a.html_fixture).read_text(encoding="utf-8") if a.html_fixture else fetch(a.url)
    result = extract(html, a.date, a.track_code, a.track, a.race, a.class_name, a.expected_cars, a.url)
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "SOURCE_OBSERVATION_ONLY", "carCount": len(result["results"]),
                      "path": a.out}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("NO_SAVE: " + str(exc), file=sys.stderr)
        sys.exit(1)
