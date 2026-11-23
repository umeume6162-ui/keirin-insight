#!/usr/bin/env python3
"""LotoPlace historical result observation (one race from venue/day page).

This is an intentionally fail-closed adapter. A heading must identify the
requested R, followed by exactly one complete 7/9-car table, with rider
identity and result status. No Google/verified writes or PASS decisions.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

EXCEPTION_LABELS = {
    "欠": "欠車", "欠車": "欠車", "取": "取消", "取消": "取消",
    "失": "失格", "失格": "失格",
    "落": "落車棄権", "落車": "落車棄権", "落車棄権": "落車棄権",
    "途": "途中棄権", "途中棄権": "途中棄権",
    "棄": "棄権", "棄権": "棄権",
}
HEADER_ALIASES = {
    "finish": {"着", "着順"},
    "number": {"車番"},
    "name": {"選手名"},
    "prefecture": {"府県"},
    "period": {"期別"},
    "grade": {"級班"},
    "method": {"決まり手", "決"},
    "exception": {"個人状況", "個人状況例外"},
}


def norm(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def compact(value):
    return re.sub(r"\s+", "", norm(value))


def validate_url(url, day, code):
    parsed = urlsplit(url)
    expected = f"/keirin/results/{int(code)}/{day}"
    allowed_hosts = ("www.lotoplace.jp", "www.chariloto.com")
    if (parsed.scheme != "https" or parsed.netloc not in allowed_hosts
            or parsed.path.rstrip("/") != expected or parsed.query or parsed.fragment):
        raise ValueError("Unsupported event-day result source URL, venue or date")
    return url


def race_number_from_label(label):
    """Recognize the published '第2レース' as well as shorthand '2R'."""
    label = compact(label)
    m = re.search(r"(?<!\d)(\d{1,2})R(?!\d)", label)
    if not m:
        m = re.search(r"第(\d{1,2})レース", label)
    return int(m.group(1)) if m else None


def grade_matches(source_grade, expected_class):
    grade = compact(source_grade)
    target = compact(expected_class)
    accepted = {
        "A3": {"A3"}, "A1A2": {"A1", "A2"},
        "S": {"S1", "S2", "SS"}, "L1": {"L1", "L2"}, "L2": {"L1", "L2"},
        "A1": {"A1", "A2"}, "A2": {"A1", "A2"}, "S1": {"S1", "S2", "SS"}, "S2": {"S1", "S2", "SS"}, "SS": {"S1", "S2", "SS"}
    }
    # A1/A2 競走 can contain both rider grades even when the sheet label is A1 or A2.
    # S1/S2 races also mix rider grades. Keep A, S and L groups separate;
    # never relax rider identity or race keys.
    if target not in accepted:
        raise ValueError("Unsupported race class for source verification")
    return grade in accepted[target]


def closest_race_number(table):
    # A whole-day page can contain many result tables. Never choose by table
    # order; look for an enclosing race section or preceding heading.
    parent = table
    for _ in range(4):
        parent = parent.parent
        if not parent:
            break
        label = compact(parent.get("data-race", ""))
        if label.isdigit():
            return int(label)
        section_id = compact(parent.get("id", ""))
        if parent.name == "section" and (m := re.fullmatch(r"race(\d{1,2})", section_id)):
            return int(m.group(1))
        if parent.name in ("section", "article"):
            headings = parent.find_all(["h2", "h3", "h4"], recursive=False)
            candidates = [compact(x.get_text(" ", strip=True)) for x in headings]
            nums = [n for text in candidates if (n := race_number_from_label(text)) is not None]
            if len(set(nums)) == 1:
                return nums[0]
    # Only a preceding explicit heading is evidence; row navigation is not.
    prev = table.find_previous(["h2", "h3", "h4"])
    if prev:
        label = compact(prev.get_text(" ", strip=True))
        number = race_number_from_label(label)
        if number is not None:
            return number
    return None


def parse_result(html, day, code, track, race, class_name, cars, url):
    date.fromisoformat(day)
    if not 1 <= int(code) <= 99 or race not in range(1, 13) or cars not in (7, 9):
        raise ValueError("Invalid race metadata")
    validate_url(url, day, code)
    soup = BeautifulSoup(html, "html.parser")
    heading = " ".join(norm(x.get_text(" ", strip=True)) for x in soup.select("title,h1"))
    if track not in heading or not (day in heading or re.search(
        rf"{int(day[:4])}年\s*{int(day[5:7])}月\s*{int(day[8:])}日", heading
    )):
        raise ValueError("Venue/date not established by title/H1")
    candidate_tables = []
    for table in soup.select("table"):
        if closest_race_number(table) != race:
            continue
        headers = {}
        rows = table.find_all("tr")
        header_at = None
        for index, tr in enumerate(rows):
            names = [compact(x.get_text(" ", strip=True))
                     for x in tr.find_all(["td", "th"], recursive=False)]
            mapping = {}
            for field, aliases in HEADER_ALIASES.items():
                matched = [i for i, value in enumerate(names) if value in aliases]
                if len(matched) == 1:
                    mapping[field] = matched[0]
            if all(f in mapping for f in ("finish", "number", "name", "prefecture", "period", "method")):
                headers, header_at = mapping, index
                break
        if header_at is None:
            continue
        parsed = []
        for tr in rows[header_at + 1:]:
            cells = tr.find_all(["th", "td"], recursive=False)
            if len(cells) <= max(headers.values()):
                continue
            car_raw = compact(cells[headers["number"]].get_text(" ", strip=True))
            if not car_raw.isdigit() or not 1 <= int(car_raw) <= cars:
                continue
            get = lambda field: compact(cells[headers[field]].get_text(" ", strip=True)) if field in headers else ""
            finished = get("finish")
            ex = get("exception")
            if finished.isdigit() and 1 <= int(finished) <= cars and not ex:
                finish = str(int(finished))
                ex = ""
            elif finished in EXCEPTION_LABELS:
                normalized_status = EXCEPTION_LABELS[finished]
                if ex and EXCEPTION_LABELS.get(ex) != normalized_status:
                    raise ValueError("Conflicting exception and finish in target race")
                finish = ex = normalized_status
            else:
                raise ValueError("Invalid finish/exception in target race")
            if "grade" not in headers or not grade_matches(get("grade"), class_name):
                raise ValueError("Rider class conflicts with requested race class")
            period = get("period").removesuffix("期")
            name, pref = norm(cells[headers["name"]].get_text(" ", strip=True)), get("prefecture")
            if len(compact(name)) < 2 or not pref or not period.isdigit():
                raise ValueError("Missing rider identity in target race")
            parsed.append(dict(number=int(car_raw), name=name, prefecture=pref,
                               period=period, finish=finish,
                               method=get("method"), exception=ex))
        if len(parsed) == cars and sorted(x["number"] for x in parsed) == list(range(1, cars + 1)):
            candidate_tables.append(sorted(parsed, key=lambda r: r["number"]))
    if len(candidate_tables) != 1:
        raise ValueError("Exactly one complete target-race result table required")
    source_id = ("chariloto-day-results" if urlsplit(url).netloc == "www.chariloto.com"
                 else "lotoplace-day-results")
    return {"sourceUrl": url, "sourceId": source_id,
            "race": {"date": day, "trackCode": str(code).zfill(2),
                     "track": track, "race": race, "className": class_name,
                     "expectedCars": cars},
            "results": candidate_tables[0],
            "provenance": "LotoPlace page observation; independent upstream not yet proven"}


def fetch(url):
    import requests
    from urllib.robotparser import RobotFileParser
    agent = "KEIRIN-INSIGHT-Research/1.0 (single public result read-only)"
    hostname = urlsplit(url).netloc
    if hostname not in ("www.lotoplace.jp", "www.chariloto.com"):
        raise ValueError("Unapproved result host")
    robots = requests.get("https://" + hostname + "/robots.txt",
                          headers={"User-Agent": agent}, timeout=15)
    if robots.status_code == 200:
        rules = RobotFileParser()
        rules.parse(robots.text.splitlines())
        if not rules.can_fetch(agent, url):
            raise ValueError("robots disallows URL")
    elif robots.status_code not in (404, 410):
        raise ValueError("robots access could not be established")
    response = requests.get(url, headers={"User-Agent": agent}, timeout=20)
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise ValueError("HTML too large")
    return response.text


def self_test():
    day, code, track, race, grade, cars = "2026-09-10", "27", "京王閣", 2, "A3", 7
    url = f"https://www.lotoplace.jp/keirin/results/27/{day}/"
    header = "<tr>" + "".join(f"<th>{v}</th>" for v in
        ("着", "車番", "選手名", "年齢", "府県", "期別", "級班", "着差", "上り", "決まり手", "S/B", "個人状況")) + "</tr>"
    row = lambda n: "<tr>" + "".join(f"<td>{v}</td>" for v in
        (n, n, f"選手{n}", 48, "京都", 93, "A3", "", "12.0", "差" if n == 1 else "", "", "")) + "</tr>"
    html = "<html><head><title>京王閣2026年9月10日レース経過･結果</title></head><body>" + (
        "<section><h2>2R チャレンジ一般</h2><table>" + header
        + "".join(row(n) for n in range(1, 8)) + "</table></section></body></html>")
    html = html.replace("<h2>2R チャレンジ一般</h2>", "<h2>第2レース A級</h2>")
    observation = parse_result(html, day, code, track, race, grade, cars, url)
    assert len(observation["results"]) == 7
    chariloto_url = f"https://www.chariloto.com/keirin/results/27/{day}"
    chariloto_html = html.replace("<section>", '<section id="race2">')
    chariloto_observation = parse_result(chariloto_html, day, code, track, race, grade, cars, chariloto_url)
    assert chariloto_observation["sourceId"] == "chariloto-day-results"
    assert len(chariloto_observation["results"]) == 7

    # A lone abbreviated exception in the finish column is sufficient;
    # do not invent a numeric finishing rank.
    falling = html.replace("<td>7</td><td>7</td>", "<td>落</td><td>7</td>")
    seen = parse_result(falling, day, code, track, race, grade, cars, url)
    assert seen["results"][-1]["finish"] == "落車棄権" and seen["results"][-1]["exception"] == "落車棄権"

    mixed = html.replace("<td>A3</td>", "<td>A1</td>")
    mixed = mixed.replace("<td>A1</td>", "<td>A2</td>", 1)
    observed_mixed = parse_result(mixed, day, code, track, race, "A2", cars, url)
    assert len(observed_mixed["results"]) == 7
    mixed_s = html.replace("<td>A3</td>", "<td>S1</td>")
    mixed_s = mixed_s.replace("<td>S1</td>", "<td>S2</td>", 1)
    assert len(parse_result(mixed_s, day, code, track, race, "S2", cars, url)["results"]) == 7
    assert grade_matches("A1", "A2") and grade_matches("A2", "A1")
    assert grade_matches("S1", "S2") and grade_matches("S2", "S1")
    assert grade_matches("SS", "S1") and grade_matches("S1", "SS")
    assert grade_matches("L2", "L1") and grade_matches("L1", "L2")
    assert not grade_matches("A1", "S2") and not grade_matches("A3", "S1")
    assert grade_matches("A3", "A3") and not grade_matches("A3", "A2")
    assert not grade_matches("S1", "A1") and not grade_matches("L1", "A2")
    try:
        parse_result(html, day, code, track, race, "S", cars, url)
    except ValueError:
        pass
    else:
        raise AssertionError("Wrong class accepted")

    for altered in (html.replace("<td>7</td><td>7</td>", "<td>7</td><td>6</td>"),
                    html.replace("<h2>第2レース", "<h2>第3レース")):
        try:
            parse_result(altered, day, code, track, race, grade, cars, url)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid result accepted")
    print("SELF_TEST_OK: LotoPlace header-labelled 7-car result, wrong-R and duplicate guards")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--date")
    p.add_argument("--track-code")
    p.add_argument("--track")
    p.add_argument("--race", type=int)
    p.add_argument("--class-name")
    p.add_argument("--expected-cars", type=int)
    p.add_argument("--url")
    p.add_argument("--html-fixture")
    p.add_argument("--out", default="/tmp/ki-lotoplace-observation.json")
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if not all((args.date, args.track_code, args.track, args.race, args.class_name,
                args.expected_cars, args.url)):
        p.error("Event identity, class, expected cars and URL are required")
    validate_url(args.url, args.date, args.track_code)
    html = Path(args.html_fixture).read_text(encoding="utf-8") if args.html_fixture else fetch(args.url)
    data = parse_result(html, args.date, args.track_code, args.track, args.race,
                        args.class_name, args.expected_cars, args.url)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "SOURCE_OBSERVATION_ONLY", "cars": len(data["results"]),
                      "output": args.out}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("NO_SAVE: " + str(exc), file=sys.stderr)
        sys.exit(1)
