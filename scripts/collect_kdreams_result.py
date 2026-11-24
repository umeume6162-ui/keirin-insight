#!/usr/bin/env python3
"""Read-only K-Dreams result observation using evidence-backed race URLs.

Never grants PASS or writes to Sheets. Requires a separately identified RESULT
table, a complete racecard identity table, exact race/date and 7/9 car coverage.
"""
import re
import unicodedata
from datetime import date
from urllib.parse import parse_qs, urlsplit

import requests
from bs4 import BeautifulSoup

from collect_lotoplace_result import EXCEPTION_LABELS, grade_matches
from compare_race_results import normalized_name, normalized_prefecture, normalized_results
from result_robots import require_robots_access

PREFECTURES = (
    "北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島",
    "茨城", "栃木", "群馬", "埼玉", "千葉", "東京", "神奈川",
    "新潟", "富山", "石川", "福井", "山梨", "長野", "岐阜",
    "静岡", "愛知", "三重", "滋賀", "京都", "大阪", "兵庫",
    "奈良", "和歌山", "鳥取", "島根", "岡山", "広島", "山口",
    "徳島", "香川", "愛媛", "高知", "福岡", "佐賀", "長崎",
    "熊本", "大分", "宮崎", "鹿児島", "沖縄",
)

def normalized(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()

def compact(value):
    return re.sub(r"\s+", "", normalized(value))

def result_url(day, code, track, race):
    # Only the observed Tamano first-day format is proved; do not invent other
    # venue/day links or infer a new meeting start date from race date.
    if code != "61" or track != "玉野":
        raise ValueError("K-Dreams URL format not yet verified for this venue")
    date.fromisoformat(day)
    if not 1 <= int(race) <= 12:
        raise ValueError("Invalid race number")
    return (f"https://keirin.kdreams.jp/tamano/racedetail/"
            f"61{day.replace('-', '')}0100{int(race):02d}/?pageType=showResult")

def validate_url(url, day, code, track, race):
    """Accept an *observed* K-Dreams race URL for any venue.

    The meeting-start date in the URL may differ from the actual race date;
    do not manufacture it. The extracted HTML title and complete rider
    identities are checked separately by extract().
    """
    parsed = urlsplit(url)
    code = str(code).zfill(2)
    match = re.fullmatch(
        r"/[a-z][a-z0-9-]*/racedetail/(" + re.escape(code)
        + r"\d{12}(\d{2}))/", parsed.path
    )
    if (parsed.scheme != "https" or parsed.netloc != "keirin.kdreams.jp"
            or parsed.username or parsed.password or parsed.fragment
            or parse_qs(parsed.query) != {"pageType": ["showResult"]}
            or match is None or int(match.group(2)) != int(race)):
        raise ValueError("Unverified K-Dreams source URL")
    date.fromisoformat(day)

def parse_identity(text):
    # The HTML presents "渡口 まりあ 山　口/32/114".
    parts = compact(text).split("/")
    if len(parts) == 3 and parts[0].endswith("外国") and len(parts[0]) > 2:
        if not re.fullmatch(r"\d{1,3}|[-—－]?", parts[1]) or not re.fullmatch(r"\d{1,3}|[-—－]?", parts[2]):
            raise ValueError("Unexpected foreign rider identity format")
        return parts[0][:-2], "外国", parts[2] if parts[2].isdigit() else ""
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        raise ValueError("Missing rider age/period in racecard")
    pre = parts[0]
    matches = [pref for pref in PREFECTURES if pre.endswith(pref)
               and len(pre) > len(pref)]
    if len(matches) != 1:
        raise ValueError("Unidentified rider prefecture")
    pref = matches[0]
    return pre[:-len(pref)], pref, parts[2]

def table_headers(table):
    first = table.find("tr")
    if first is None:
        return []
    return [compact(c.get_text(" ", strip=True))
            for c in first.find_all("th", recursive=False)]

def exact_table(soup, needed):
    found = []
    for table in soup.select("table"):
        heads = table_headers(table)
        if len(heads) < len(needed) or any(heads.count(v) != 1 for v in needed):
            continue
        found.append((table, {v: heads.index(v) for v in needed}))
    if len(found) != 1:
        raise ValueError("Exactly one complete target-race result table required")
    return found[0]

def extract(html, day, code, track, race, class_name, cars, url):
    validate_url(url, day, code, track, race)
    if cars not in (7, 9):
        raise ValueError("Unsupported field size")
    soup = BeautifulSoup(html, "html.parser")
    title = compact(soup.title.get_text(" ", strip=True) if soup.title else "")
    stamp = f"{int(day[:4])}年{int(day[5:7])}月{int(day[8:])}日"
    if (track + "競輪" not in title or stamp not in title
            or not re.search(rf"(?<!\d){int(race)}R(?!\d)", title)):
        raise ValueError("Race date/venue not found in title")
    entry, _ = exact_table(soup, ("車番", "選手名府県/年齢/期別", "級班", "直近4ヶ月の成績"))
    expected = {}
    for tr in entry.find_all("tr")[1:]:
        cells = tr.find_all("td", recursive=False)
        # The public table omits an empty prediction cell for some riders.
        # Anchor to the source-labelled identity cell, not a fragile td index.
        identities = [i for i, cell in enumerate(cells)
                      if re.fullmatch(r"(?:.+/\d{1,3}/\d{2,3}|.+外国/(?:\d{1,3}|[-—－]?)/(?:\d{1,3}|[-—－]?))",
                                      compact(cell.get_text(" ", strip=True)))]
        if not identities:
            continue  # heading/guide/footer row, not a rider
        if len(identities) != 1 or identities[0] == 0 or identities[0] + 1 >= len(cells):
            raise ValueError("Ambiguous rider identity in racecard")
        i = identities[0]
        car = compact(cells[i - 1].get_text(" ", strip=True))
        if not car.isdigit() or not 1 <= int(car) <= cars:
            raise ValueError("Invalid car number adjacent to rider identity")
        num = int(car)
        if num in expected:
            raise ValueError("Duplicate car in racecard")
        name, pref, period = parse_identity(cells[i].get_text(" ", strip=True))
        grade = compact(cells[i + 1].get_text(" ", strip=True))
        if not grade_matches(grade, class_name) and not (pref == "外国" and grade in ("", "-", "—", "外国")):
            raise ValueError("Rider class conflicts with requested race class")
        expected[num] = (normalized_name(name), normalized_prefecture(pref), period)
    if sorted(expected) != list(range(1, cars + 1)):
        raise ValueError("Incomplete pre-race rider identity in source")

    table, idx = exact_table(soup, ("着順", "車番", "選手名", "決まり手"))
    results = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td", recursive=False)
        if len(cells) <= max(idx.values()):
            continue
        car_raw = compact(cells[idx["車番"]].get_text(" ", strip=True))
        if not car_raw.isdigit() or not 1 <= int(car_raw) <= cars:
            continue
        num = int(car_raw)
        finish = compact(cells[idx["着順"]].get_text(" ", strip=True))
        state = ""
        if finish.isdigit() and 1 <= int(finish) <= cars:
            finish = str(int(finish))
        elif finish in EXCEPTION_LABELS:
            state = finish = EXCEPTION_LABELS[finish]
        else:
            raise ValueError("Invalid finish/exception in target race")
        raw_name = cells[idx["選手名"]].get_text(" ", strip=True)
        name, pref, period = expected[num]
        if normalized_name(raw_name) != name:
            raise ValueError("Rider identity does not match pre-race source")
        result = dict(number=num, name=name, prefecture=pref,
                      period=period, finish=finish,
                      method=compact(cells[idx["決まり手"]].get_text(" ", strip=True)),
                      exception=state)
        if pref == "外国":
            result["invitedEvidence"] = dict(
                kind="foreign_invited", number=num, entryName=name,
                raceKey=f"{day}|{str(code).zfill(2)}|{int(race)}",
                entryUrl=url, statusSourceUrl=url,
                evidenceRef=f"K-Dreams racecard car {num}: 府県=外国",
                rawPrefecture=pref, rawPeriod=period)
        results.append(result)
    if (len(results) != cars or
            sorted(x["number"] for x in results) != list(range(1, cars + 1))):
        raise ValueError("Exactly one complete target-race result table required")
    return {"sourceUrl": url, "sourceId": "kdreams-race-result",
            "race": {"date": day, "trackCode": str(code).zfill(2),
                     "track": track, "race": int(race), "className": class_name,
                     "expectedCars": cars}, "results": sorted(results, key=lambda r: r["number"]),
            "provenance": "K-Dreams HTML, independent upstream not yet proven"}

def fetch(url):
    agent = "KEIRIN-INSIGHT-Research/1.0 (single public result read-only)"
    require_robots_access(url, "keirin.kdreams.jp", agent)
    response = requests.get(url, headers={"User-Agent": agent}, timeout=20)
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise ValueError("Source HTML too large")
    return response.text

def self_test():
    day, code, track, race, grade, cars = "2026-11-23", "61", "玉野", 1, "L1", 7
    url = result_url(day, code, track, race)
    assert url.endswith("6120261123010001/?pageType=showResult")
    # The published URL is evidence: never infer meeting day from race day.
    another = "https://keirin.kdreams.jp/kurume/racedetail/8320261001010003/?pageType=showResult"
    validate_url(another, "2026-10-01", "83", "久留米", 3)
    # Regression: a valid observed multi-venue result URL must survive the guard.
    assert re.fullmatch(r"/kurume/racedetail/83\d{12}(\d{2})/", urlsplit(another).path)

    for bad in (another.replace("0003/", "0004/"),
                another.replace("keirin.kdreams.jp", "evil.example"),
                another + "&other=1"):
        try:
            validate_url(bad, "2026-10-01", "83", "久留米", 3)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe/wrong-R discovered URL accepted")

    head = "<title>玉野競輪 レース詳細 | 1R | 2026年11月23日</title>"
    ehead = "<tr>" + "".join("<th>" + x + "</th>" for x in
        ("予 想", "車 番", "選手名 府県/年齢/期別", "級 班", "直近4ヶ月の成績")) + "</tr>"
    rhead = "<tr>" + "".join("<th>" + x + "</th>" for x in
        ("着 順", "車 番", "選手名", "決ま り手")) + "</tr>"
    ers = "".join(f"<tr><td></td><td>{n}</td><td>選手 {n} 埼　玉/30/90</td><td>L1</td><td></td></tr>"
                  for n in range(1, 8))
    rrs = "".join(f"<tr><td>{n}</td><td>{n}</td><td>選手 {n}</td><td>{'差' if n==1 else ''}</td></tr>"
                  for n in range(1, 8))
    html = f"<html><head>{head}</head><body><table>{ehead}{ers}</table><table>{rhead}{rrs}</table></body></html>"
    obs = extract(html, day, code, track, race, grade, cars, url)
    assert len(obs["results"]) == 7 and obs["results"][0]["prefecture"] == "埼玉"
    assert obs["results"][0]["method"] == "差"
    # Synthetic fixtures exercise the explicit row-level foreign marker only.
    for original in ("外国/30/999", "外国/30/-", "外国//"):
        guest_html = html.replace("埼　玉/30/90", original, 1)
        guest = extract(guest_html, day, code, track, race, grade, cars, url)
        assert guest["results"][0]["prefecture"] == "外国"
        assert guest["results"][0]["invitedEvidence"]["raceKey"] == day+"|61|1"
        assert len(normalized_results(guest, cars)) == cars
    domestic = extract(html.replace("埼　玉/30/90", "埼　玉/30/999", 1),
                       day, code, track, race, grade, cars, url)
    assert "invitedEvidence" not in domestic["results"][0]
    for bad in (html.replace("埼　玉/30/90", "埼　玉/30/-", 1),
                html.replace("埼　玉/30/90", "外国/30/999", 1).replace("選手 1</td>", "別人</td>")):
        try:
            extract(bad, day, code, track, race, grade, cars, url)
        except ValueError:
            pass
        else:
            raise AssertionError("Unproved or mismatched rider accepted")
    for invalid in (html.replace("選手 7</td>", "別人</td>"),
                    html.replace("<td>7</td><td>7</td>", "<td>7</td><td>6</td>"),
                    html.replace("1R |", "2R |")):
        try:
            extract(invalid, day, code, track, race, grade, cars, url)
        except ValueError:
            pass
        else:
            raise AssertionError("Incomplete/wrong-race result accepted")
    print("SELF_TEST_OK: K-Dreams full result + pre-race identity, wrong-R and duplicates")

if __name__ == "__main__":
    self_test()
