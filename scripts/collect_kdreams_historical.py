#!/usr/bin/env python3
"""Historical K-Dreams *read-only* result adapter.

Existing daily K-Dreams collector remains untouched. This shim fixes URL
recognition only inside the historical extraction call. It NEVER promotes
PASS, edits Sheets, or writes official feeds. It can parse preserved HTML or
probe one explicitly supplied public URL (robots checked by existing fetch).
"""
import argparse
import json
import re
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import collect_kdreams_result as kdreams


def validate_historical_url(url, day, code, track, race):
    """Validate an OBSERVED URL; never synthesize its meeting-start date."""
    from datetime import date
    date.fromisoformat(day)
    code = str(code).zfill(2)
    path = urlsplit(url)
    match = re.fullmatch(
        r"/[a-z][a-z0-9-]*/racedetail/" + re.escape(code)
        + r"\d{12}(\d{2})/", path.path
    )
    query = parse_qs(path.query, keep_blank_values=True)
    if (path.scheme != "https" or path.netloc != "keirin.kdreams.jp"
            or path.username or path.password or path.fragment
            or match is None or int(match.group(1)) != int(race)
            or query not in (
                {"pageType": ["showResult"]},
                {"pageType": ["KS_RACE_CARD_PAGE_TYPE_SHOW_RESULT"]},
            )):
        raise ValueError("Historical K-Dreams URL rejected")


def parse_historical_html(html, *, url, day, code, track, race, grade, cars):
    validate_historical_url(url, day, code, track, race)
    # K-Dreams real titles often zero-pad the day: 2026年10月05日.
    # Only normalize the *title date* AFTER confirming it denotes the exact
    # requested day; never rewrite the date, racecard, or result rows.
    from datetime import date
    d = date.fromisoformat(day)
    soup = BeautifulSoup(html, "html.parser")
    if soup.title is None:
        raise ValueError("Missing race source title")
    title = soup.title.get_text(" ", strip=True)
    date_in_title = re.findall(r"(?<!\\d)(\\d{4})年(\\d{1,2})月(\\d{1,2})日", title)
    if len(date_in_title) != 1 or tuple(map(int,date_in_title[0])) != (
            d.year,d.month,d.day):
        raise ValueError("Race date mismatch in original K-Dreams title")
    # The pre-existing parser checks an unpadded literal date string. Update
    # only a temporary parsed copy to maintain the unchanged shared parser.
    source_date = "".join((str(d.year), "年", str(d.month), "月", str(d.day), "日"))
    source_title_date = re.search(r"(?<!\\d)\\d{4}年\\d{1,2}月\\d{1,2}日",title)
    soup.title.string = title[:source_title_date.start()] + source_date + title[source_title_date.end():]
    html = str(soup)
    # Avoid changing the daily collector. Its extraction does full source table
    # checks and calls validate_url internally; override only for this call.
    with patch.object(kdreams, "validate_url", validate_historical_url):
        observation = kdreams.extract(
            html, day, str(code).zfill(2), track, int(race), grade, int(cars), url
        )
    assert len(observation["results"]) == int(cars)
    assert sorted(int(x["number"]) for x in observation["results"]) == list(
        range(1, int(cars) + 1)
    )
    return {
        "schema": "ki-kdreams-historical-observation-v1",
        "verificationState": "SOURCE_OBSERVED_NOT_FORMAL_PASS",
        "observation": observation,
        "sourceProof": {
            "kind": "preserved_original_html",
            "sourceUrl": url,
            "note": "HTML input must be an actual page preserved with reliable date and origin.",
        },
    }


def self_test():
    urls = (
        "https://keirin.kdreams.jp/tamano/racedetail/6120261123010001/?pageType=showResult",
        "https://keirin.kdreams.jp/matsuyama/racedetail/7520261004020004/?pageType=KS_RACE_CARD_PAGE_TYPE_SHOW_RESULT",
    )
    validate_historical_url(urls[0], "2026-11-23", "61", "玉野", 1)
    validate_historical_url(urls[1], "2026-10-05", "75", "松山", 4)
    for bad in (
        urls[0].replace("0001/", "0002/"),
        urls[0].replace("keirin.kdreams.jp", "evil.example"),
        urls[0] + "&other=1",
        urls[1].replace("75", "76", 1),
    ):
        try:
            validate_historical_url(bad, "2026-11-23", "61", "玉野", 1)
        except ValueError:
            continue
        raise AssertionError("Invalid K-Dreams historical URL accepted")
    # Source parser integration, no network: use a small full 7-car fixture.
    head = "<title>玉野競輪 レース詳細 | 1R | 2026年11月23日</title>"
    entry_head = "<tr>" + "".join("<th>"+x+"</th>" for x in
        ("予 想","車 番","選手名 府県/年齢/期別","級 班","直近4ヶ月の成績")) + "</tr>"
    result_head = "<tr>" + "".join("<th>"+x+"</th>" for x in
        ("着 順","車 番","選手名","決ま り手")) + "</tr>"
    entries = "".join(f"<tr><td></td><td>{n}</td><td>選手 {n} 埼　玉/30/90</td><td>L1</td><td></td></tr>"
                      for n in range(1,8))
    results = "".join(f"<tr><td>{n}</td><td>{n}</td><td>選手 {n}</td><td>{'差' if n==1 else ''}</td></tr>"
                      for n in range(1,8))
    html = f"<html><head>{head}</head><body><table>{entry_head}{entries}</table><table>{result_head}{results}</table></body></html>"
    result = parse_historical_html(html, url=urls[0], day="2026-11-23",
        code="61", track="玉野", race=1, grade="L1", cars=7)
    assert len(result["observation"]["results"]) == 7
    assert result["verificationState"] == "SOURCE_OBSERVED_NOT_FORMAL_PASS"
    padded = html.replace("2026年11月23日","2026年11月023日")
    try:
        parse_historical_html(padded,url=urls[0],day="2026-11-23",
                              code="61",track="玉野",race=1,grade="L1",cars=7)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid 3-digit day passed")
    padded_valid = html.replace("2026年11月23日","2026年11月23日")
    assert len(parse_historical_html(padded_valid,url=urls[0],day="2026-11-23",
              code="61",track="玉野",race=1,grade="L1",cars=7)["observation"]["results"]) == 7
    wrong = html.replace("2026年11月23日", "2026年11月22日")
    try:
        parse_historical_html(wrong,url=urls[0],day="2026-11-23",
                              code="61",track="玉野",race=1,grade="L1",cars=7)
    except ValueError:
        pass
    else:
        raise AssertionError("Wrong event date passed")
    print("SELF_TEST_OK: historical K-Dreams URL variants, full 7-car parser; daily unchanged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--date")
    parser.add_argument("--track-code")
    parser.add_argument("--track")
    parser.add_argument("--race", type=int)
    parser.add_argument("--class-name")
    parser.add_argument("--cars", type=int)
    parser.add_argument("--url")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--html-file")
    group.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not all([args.date,args.track_code,args.track,args.race,args.class_name,args.cars,args.url]):
        parser.error("date, track-code, track, race, class-name, cars, URL required")
    if not args.html_file and not args.fetch:
        parser.error("specify --html-file (preserved source) or --fetch (one live public page)")
    validate_historical_url(args.url,args.date,args.track_code,args.track,args.race)
    html = Path(args.html_file).read_text(encoding="utf-8") if args.html_file else kdreams.fetch(args.url)
    result = parse_historical_html(html,url=args.url,day=args.date,code=args.track_code,
        track=args.track,race=args.race,grade=args.class_name,cars=args.cars)
    if args.fetch:
        result["sourceProof"]["kind"] = "live_html"
        result["sourceProof"]["note"] = "Read-only live HTTP observation; HTML has not been preserved."
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
