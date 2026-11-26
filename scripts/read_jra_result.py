#!/usr/bin/env python3
"""Read and validate a public JRA flat-race result into private-ledger row shape.

Requires lxml. Pair official result URLs with --race numbers in order, or
pass one result URL with --discover to resolve requested races. Outputs JSON.
"""
import argparse
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
import json
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

from lxml import html

HOST = "www.jra.go.jp"
AGENT = "Race-Insight-Research/1.0"
VENUES = dict(zip(
    ("札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"),
    ("SAPPORO", "HAKODATE", "FUKUSHIMA", "NIIGATA", "TOKYO", "NAKAYAMA",
     "CHUKYO", "KYOTO", "HANSHIN", "KOKURA"),
))
COLUMNS = {"place", "waku", "num", "horse", "age", "weight", "jockey", "time",
           "margin", "corner", "f_time", "h_weight", "trainer", "pop"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@lru_cache(maxsize=1)
def jra_access():
    opener = build_opener(NoRedirect)
    policy_url = f"https://{HOST}/robots.txt"
    with opener.open(Request(policy_url, headers={"User-Agent": AGENT}), timeout=15) as response:
        raw = response.read(65537)
    if len(raw) > 65536 or not re.search(rb"(?im)^User-agent:", raw):
        raise ValueError("JRA robots policy could not be verified")
    policy = RobotFileParser(policy_url)
    policy.parse(raw.decode("utf-8").splitlines())
    return opener, policy


def result_key(url):
    source = urlsplit(url)
    query = parse_qs(source.query)
    if (source.scheme != "https" or source.netloc != HOST or source.fragment
            or source.path != "/JRADB/accessS.html" or set(query) != {"CNAME"}
            or len(query["CNAME"]) != 1):
        raise ValueError("Expected an official JRA result URL")
    key = re.fullmatch(r"pw01sde(\d{12})(0[1-9]|1[0-2])(\d{8})/[A-F0-9]{2}", query["CNAME"][0])
    if not key:
        raise ValueError("Invalid JRA result identifier")
    return key


def fetch_page(url, form=None):
    opener, policy = jra_access()
    if not policy.can_fetch(AGENT, url):
        raise ValueError("JRA robots policy disallows page")
    with opener.open(Request(url, data=form, headers={"User-Agent": AGENT}), timeout=20) as response:
        data = response.read(2000001)
    if len(data) > 2000000:
        raise ValueError("JRA page exceeds the size limit")
    return data


def read_result(url):
    result_key(url)
    return fetch_page(url)


def one(nodes, field):
    if len(nodes) != 1:
        raise ValueError(f"Expected one {field}")
    return nodes[0]


def wording(node):
    return " ".join(node.text_content().split())


def meeting_header(doc, day, venue, race):
    header = one(doc.xpath('//div[@class="race_header"]'), "race header")
    meeting = wording(one(header.xpath('.//div[@class="cell date"]'), "meeting date"))
    stamp = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日（[^）]+）\s*(\d+)回(.+?)(\d+)日", meeting)
    number = header.xpath('.//div[@class="race_number"]/img/@alt')
    if (not stamp or date(*map(int, stamp.groups()[:3])) != day
            or stamp[5] != venue or number != [f"{race}レース"]):
        raise ValueError("Published JRA meeting date, venue or race number differs")
    return header, stamp


def discovery_links(seed, seed_url, day, venue):
    doc = html.fromstring(seed)
    meeting_header(doc, day, venue, int(result_key(seed_url)[2]))
    actions = set()
    for link in doc.xpath('//a[@onclick]'):
        if wording(link) not in {"レース選択へ戻る", "レース結果 レース選択"}:
            continue
        action = re.search(r"doAction\('/JRADB/accessS.html',\s*'(pw01srl(\d{12})(\d{8})/[A-F0-9]{2})'\)",
                           link.get("onclick", ""))
        if action and action[3] == day.strftime("%Y%m%d"):
            actions.add((action[1], action[2], action[3]))
    token, meeting, day_key = one(list(actions), "same-meeting selection link")
    endpoint = f"https://{HOST}/JRADB/accessS.html"
    listing = html.fromstring(fetch_page(endpoint, urlencode({"CNAME": token}).encode("ascii")))
    links = {}
    for link in listing.xpath('//a[contains(@href,"pw01sde")][img]'):
        marker = link.xpath('./img/@alt')
        if len(marker) != 1 or not re.fullmatch(r"(?:[1-9]|1[0-2])レース", marker[0]):
            continue
        url = urljoin(endpoint, link.get("href"))
        key = result_key(url)
        number = int(key[2])
        if (key[1], key[3]) != (meeting, day_key) or marker[0] != f"{number}レース":
            raise ValueError("Result listing contains a mismatched race link")
        if links.setdefault(number, url) != url:
            raise ValueError("Result listing contains conflicting links")
    if not links:
        raise ValueError("Official selection page lists no results")
    return links


def parse_result(data, url, day, venue, race, acquired):
    doc = html.fromstring(data)
    header, stamp = meeting_header(doc, day, venue, race)
    context = wording(one(header.xpath('.//div[@class="cell course"]'), "course"))
    course = re.fullmatch(r"コース：([0-9,]+)メートル（(芝|ダート)・(右|左|直線)(?:[ 　]+(内|外))?）", context)
    if not course:
        raise ValueError("Course layout is outside the supported flat-race format")
    meters = int(course[1].replace(",", ""))
    surface = course[2]
    direction = "・".join(part for part in course.groups()[2:] if part)
    weather = wording(one(header.xpath('.//li[@class="weather"]//span[@class="txt"]'), "weather"))
    going = wording(one(header.xpath('.//li[.//span[@class="cap" and text()=$surface]]//span[@class="txt"]',
                                     surface=surface), "going"))
    label = wording(one(header.xpath('.//h2//span[@class="race_name"]'), "race name"))
    label = re.sub(r"^第\d+回", "", label)
    age = wording(one(header.xpath('.//div[@class="cell category"]'), "age condition"))
    grade = wording(one(header.xpath('.//div[@class="cell class"]'), "class"))
    grade_mark = header.xpath('.//h2//img/@alt')
    if grade_mark:
        grade = {"GⅠ": "GI", "GⅡ": "GII", "GⅢ": "GIII", "リステッド": "L"}.get(grade_mark[0], "")
        if not grade:
            raise ValueError("Unknown race grade")
    conditions = header.xpath('.//div[@class="cell rule"]')
    rule = wording(conditions[0]) if conditions else ""
    kind = ("国際" if "国際" in rule else "混合" if "混合" in rule else
            "牝馬限定" if re.search("牝(?:$|[［（])", rule) else "若手騎手" if "若手騎手" in rule else None)
    result_table = one(doc.xpath('//table[thead/tr/th[@class="horse"] and thead/tr/th[@class="place"]]'),
                       "results table")
    race_id = f"{day.isoformat()}-{VENUES[venue]}-{race:02}"
    horses = []
    for row in result_table.xpath("./tbody/tr"):
        cells = {n.get("class"): n for n in row.xpath("./td")}
        if not COLUMNS <= cells.keys():
            raise ValueError("Result row has an incomplete column set")
        cell = {k: wording(v) for k, v in cells.items()}
        sex_age = re.fullmatch(r"(牡|牝|せん)(\d+)", cell["age"])
        mass = re.fullmatch(r"(\d+)\(([+-]?\d+|初出走)\)", cell["h_weight"])
        frame = cells["waku"].xpath('./img/@alt')
        finish = cell["place"]
        if not sex_age or not mass or not frame or not finish.isdigit():
            raise ValueError("Unsupported cancellation, abnormal result or missing result measurement")
        positions = [None] * 4
        for node in cells["corner"].xpath(".//li"):
            corner = re.fullmatch(r"([1-4])コーナー通過順位", node.get("title", ""))
            if not corner or positions[int(corner[1]) - 1] is not None:
                raise ValueError("Unrecognized or duplicate corner")
            positions[int(corner[1]) - 1] = int(wording(node))
        if not all(cell[k] for k in ("horse", "jockey", "time", "trainer")):
            raise ValueError("Missing horse, rider, time or trainer")
        horses.append([race_id, None, int(cell["num"]), int(re.match(r"枠([1-8])", frame[0])[1]),
                       cell["horse"], int(sex_age[2]), sex_age[1], float(cell["weight"]),
                       cell["jockey"].lstrip("▲△☆★◇◆"), cell["trainer"], finish, cell["time"],
                       cell["margin"] or None, *positions, float(cell["f_time"]), int(cell["pop"]),
                       int(mass[1]), None if mass[2] == "初出走" else int(mass[2]),
                       None, None, None, acquired, url, "JRA公式結果確認・馬ID未照合"])
    count = len(horses)
    expected = list(range(1, count + 1))
    if not 1 <= count <= 18 or sorted(row[2] for row in horses) != expected:
        raise ValueError("Result horse numbers are incomplete or duplicated")
    if [int(row[10]) for row in horses] != expected:
        raise ValueError("Tied or non-sequential finish requires review")
    positions = [n for n in doc.xpath('//th') if re.match(r"^[1-4]コーナー", wording(n))]
    if not positions or any(sorted(map(int, re.findall(r"\d+", wording(n.getnext())))) != expected
                            for n in positions):
        raise ValueError("Official corner table does not corroborate the full field")
    timing = {wording(n): wording(n.getnext()) for n in doc.xpath('//tbody/tr/th')
              if wording(n) in {"ハロンタイム", "上り"}}
    segments = [Decimal(x) for x in timing["ハロンタイム"].split(" - ")]
    final = Decimal(re.search(r"3F (\d+\.\d+)", timing["上り"])[1])
    if len(segments) != (meters + 199) // 200 or sum(segments[-3:]) != final:
        raise ValueError("Official race segments and finishing 600m differ")
    front = None if meters % 200 else float(sum(segments[:3]))
    ledger = [race_id, day.isoformat(), venue, int(stamp[4]), int(stamp[6]), race,
              label, kind, age, grade, surface, meters, direction, going, weather,
              count, None, front, float(final), horses[0][11], None, None, None, acquired, url,
              f"JRA公式確認・全{count}頭収録・馬ID未照合"]
    return {"race": ledger, "horses": horses}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("urls", nargs="+")
    p.add_argument("--date", required=True, type=date.fromisoformat)
    p.add_argument("--venue", required=True, choices=VENUES)
    p.add_argument("--race", required=True, action="append", type=int, choices=range(1, 13))
    p.add_argument("--discover", action="store_true",
                   help="Discover requested races from one known result URL of the same meeting")
    args = p.parse_args()
    if len(set(args.race)) != len(args.race):
        p.error("Race numbers must be distinct")
    if len(args.urls) != (1 if args.discover else len(args.race)):
        p.error("Provide one seed URL with --discover or one URL per race")
    reused = {}
    urls = dict(zip(args.race, args.urls))
    if args.discover:
        seed_url = args.urls[0]
        try:
            seed = read_result(seed_url)
            urls = discovery_links(seed, seed_url, args.date, args.venue)
            seed_race = int(result_key(seed_url)[2])
            if seed_race in urls:
                reused[seed_race] = seed
                urls[seed_race] = seed_url
        except (OSError, ValueError, KeyError, IndexError, AttributeError) as exc:
            p.exit(1, f"JRA meeting selection held: {exc}\n")
    acquired = datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()
    results, holds = [], []
    for race in args.race:
        try:
            url = urls.get(race)
            if not url:
                raise ValueError("Result has no published link on the official selection page")
            data = reused[race] if race in reused else read_result(url)
            results.append(parse_result(data, url, args.date, args.venue, race, acquired))
        except (OSError, ValueError, KeyError, IndexError, ArithmeticError, AttributeError) as exc:
            holds.append({"race": race, "reason": str(exc)})
    print(json.dumps({"results": results, "holds": holds}, ensure_ascii=False))
    if holds:
        p.exit(1)


if __name__ == "__main__":
    main()
