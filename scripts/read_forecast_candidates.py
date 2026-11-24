#!/usr/bin/env python3
"""Read-only retrieval of candidate forecast pages; never grants formal PASS."""
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import requests
from bs4 import BeautifulSoup
from result_robots import require_robots_access

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from plan_missing_lines import queue

HOST = "sp.oddspark.com"
AGENT = "KEIRIN-INSIGHT-Research/1.0"
def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def venue_slugs(lines):
    found = {}
    for race in lines["races"]:
        url = race.get("officialVerification", {}).get("source", "")
        p = urlsplit(url)
        m = re.fullmatch(r"/keirin/yosou/([a-z]+)/\d{4}/\d{4}(?:_\d{1,2})?\.html", p.path)
        if p.scheme == "https" and p.netloc == HOST and m:
            code = (race.get("key") or race["id"]).split("|")[1]
            found.setdefault(code, set()).add(m.group(1))
    return {code: next(iter(slugs)) for code, slugs in found.items() if len(slugs) == 1}

def candidate_url(c, slugs):
    day, code, race = c["key"].split("|")
    d = datetime.strptime(day, "%Y-%m-%d")
    if code not in slugs or not 1 <= int(race) <= 12:
        return None
    suffix = "" if int(race) == 1 else "_" + str(int(race))
    return f"https://{HOST}/keirin/yosou/{slugs[code]}/{d:%Y}/{d:%m%d}{suffix}.html"

def meeting_prefixes(lines):
    found = {}
    for item in lines["races"]:
        day, code, race = (item.get("key") or item["id"]).split("|")
        p = urlsplit(item.get("officialVerification", {}).get("source", ""))
        if p.scheme != "https" or p.netloc != "keirin.kdreams.jp":
            continue
        m = re.fullmatch(r"(/gamboo/keirin-kaisai/race-card/yoso/"+code+r"\d{8}/"+code+r"\d{12}/)(\d{1,2})/", p.path)
        if m and int(m.group(2)) == int(race):
            found.setdefault((day,code),set()).add((m.group(1),"/"))
        m = re.fullmatch(r"(/[a-z][a-z0-9-]*/racedetail/"+code+r"\d{12})(\d{2})/", p.path)
        if m and int(m.group(2)) == int(race):
            found.setdefault((day,code),set()).add((m.group(1),"padded"))
    return found

def source_urls(c, slugs, meetings):
    day, code, race = c["key"].split("|")
    if not 1 <= int(race) <= 12:
        return []
    urls = []
    for prefix, style in sorted(meetings.get((day,code),set())):
        suffix = f"{int(race):02d}/" if style == "padded" else f"{int(race)}/"
        urls.append("https://keirin.kdreams.jp"+prefix+suffix)
    odds = candidate_url(c,slugs)
    if odds:
        urls.append(odds)
    # Netkeirin race IDs use the actual race date, venue code and race number.
    # This is a candidate URL only, not evidence of a published forecast.
    date_key = datetime.strptime(day, "%Y-%m-%d").strftime("%Y%m%d")
    if re.fullmatch(r"\d{2}", code):
        urls.append(f"https://keirin.netkeiba.com/race/yoso/?race_id={date_key}{code}{int(race):02d}")
        urls.append(f"https://keirin.netkeiba.com/race/entry/?race_id={date_key}{code}{int(race):02d}")
    return urls

def gamboo_groups(soup, size):
    """Observed explicit DOM boundaries only; unknown/contested markup is held."""
    blocks = soup.select("dl.line_position .line_position_inner")
    if len(blocks) != 1 or size not in (7, 9):
        return None
    groups, current = [], []
    for item in blocks[0].find_all(recursive=False):
        classes = set(item.get("class", []))
        if item.name != "span" or "icon_p" not in classes:
            return None
        if classes == {"icon_p", "space"} and not item.get_text(strip=True) and not item.find():
            if current:
                groups.append(current)
                current = []
            continue
        if classes != {"icon_p"}:
            return None
        children = item.find_all(recursive=False)
        if len(children) == 1 and children[0].get("class") == ["p000"] and children[0].get_text(strip=True) == "←" and not groups and not current:
            continue
        if len(children) != 2 or any(x.name != "span" or x.find() for x in children):
            return None
        num = children[0].get_text(strip=True)
        if not re.fullmatch(r"[1-9]", num) or children[0].get("class") != ["p00"+num]:
            return None
        if children[1].get("class") != ["p201"] or children[1].get_text(strip=True) not in ("先行", "自在", "追込", "捲り", "差し", "マーク", "自力", "追走"):
            return None
        current.append(int(num))
    if current:
        groups.append(current)
    return groups if sorted(n for g in groups for n in g) == list(range(1, size+1)) else None

def netkeirin_groups(soup, size):
    blocks = soup.select(".DeployYosoIn .DeployYosoWrap > .DeployBox")
    if len(blocks) != 1 or size not in (7, 9):
        return None
    groups, current = [], []
    for item in blocks[0].find_all(recursive=False):
        if item.name != "div" or item.get("class") != ["DeployInBox"]:
            return None
        children = item.find_all(recursive=False)
        if len(children) != 1 or children[0].get("class") != ["Shaban_InBox"]:
            return None
        box = children[0]
        numbers = box.select(".Shaban_Num")
        separators = box.select(".WakuSeparat")
        if len(separators) == 1 and not numbers and not box.get_text(strip=True):
            if not current:
                return None
            groups.append(current)
            current = []
        elif len(numbers) == 1 and not separators:
            n = numbers[0].get_text(strip=True)
            if not re.fullmatch(r"[1-9]", n):
                return None
            current.append(int(n))
        else:
            return None
    if not current:
        return None
    groups.append(current)
    return groups if sorted(n for g in groups for n in g) == list(range(1, size+1)) else None

def inspect(html, candidate=None):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    # Diagnostic excerpts only; never infer line boundaries from whitespace.
    excerpts = []
    structures = []
    for node in soup.find_all(string=re.compile("並び予想|ライン予想|並び想定")):
        parent = node.parent
        if parent.name in ("script", "style"):
            continue
        block = parent.parent or parent
        value = block.get_text(" ", strip=True)
        if value not in excerpts:
            excerpts.append(value[:1200])
            # Preserve the published element hierarchy, not inferred groups.
            structures.append(str(block)[:12000])
        if len(excerpts) >= 5:
            break
    # Preserve labelled table rows for subsequent exact identity comparison.
    tables = []
    for table in soup.find_all("table"):
        heads = [th.get_text(" ", strip=True) for th in table.find_all("th")[:30]]
        if not any("選手名" in re.sub(r"\s+", "", h) for h in heads) and not ("netkeiba" in title.lower() and len(table.find_all("tr")) >= 7):
            continue
        rows = []
        for tr in table.find_all("tr")[:20]:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th","td"], recursive=False)]
            if cells:
                rows.append(cells)
        tables.append({"headers":heads,"rows":rows})
        if len(tables) >= 3:
            break
    # Preserve same-race entry identity tables as well as the published forecast.
    identity_links = [a.get("href") for a in soup.select("a[href]") if "/race/shutuba/" in a.get("href", "") or "/race/entry/" in a.get("href", "")][:20]
    # Keep compact racecard observations including full identity text if published.
    return {"identityLinks": identity_links, "title": title, "gambooGroupCandidate": gamboo_groups(soup, candidate.get("size")) if candidate else None, "netkeirinGroupCandidate": netkeirin_groups(soup, candidate.get("size")) if candidate else None, "forecastLabelContexts": excerpts,
            "forecastElementHtml": structures, "riderTableObservations": tables}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        lines = {"races":[{"id":"2026-01-01|85|2","officialVerification":{"source":"https://sp.oddspark.com/keirin/yosou/sasebo/2026/0101_2.html"}}]}
        slugs = venue_slugs(lines)
        assert candidate_url({"key":"2026-01-02|85|1"},slugs).endswith("/0102.html")
        assert candidate_url({"key":"2026-01-02|85|6"},slugs).endswith("/0102_6.html")
        assert candidate_url({"key":"2026-01-02|22|6"},slugs) is None
        assert inspect("<title>sample</title><div><b>並び予想</b>①②／③</div>")["forecastLabelContexts"]
        lines["races"].append({"id":"2026-01-02|85|3","officialVerification":{"source":"https://keirin.kdreams.jp/gamboo/keirin-kaisai/race-card/yoso/8520260101/85202601010200/3/"}})
        meetings = meeting_prefixes(lines)
        assert source_urls({"key":"2026-01-02|85|6"},slugs,meetings)[0].endswith("/85202601010200/6/")
        assert len(source_urls({"key":"2026-01-03|85|6"},slugs,meetings)) == 3
        assert source_urls({"key":"2026-01-02|22|6"},slugs,meetings) == ["https://keirin.netkeiba.com/race/yoso/?race_id=202601022206", "https://keirin.netkeiba.com/race/entry/?race_id=202601022206"]
        observed = inspect('<div><b>並び予想</b><span class="test-group">①②</span><span>③</span></div><table><tr><th>選手名</th></tr><tr><td>試験選手</td></tr></table>')
        assert 'class="test-group"' in observed["forecastElementHtml"][0]
        assert observed["riderTableObservations"][0]["rows"][1] == ["試験選手"]
        fixture = '<dl class="line_position"><dd><div class="line_position_inner">' + ''.join('<span class="icon_p"><span class="p00'+str(n)+'">'+str(n)+'</span><span class="p201">先行</span></span>' + ('<span class="icon_p space"></span>' if n in (3,5) else '') for n in range(1,8)) + '</div></dd></dl>'
        assert inspect(fixture, {"size":7})["gambooGroupCandidate"] == [[1,2,3],[4,5],[6,7]]
        assert inspect(fixture.replace('p003','p002'), {"size":7})["gambooGroupCandidate"] is None
        nk = '<div class="DeployYosoIn"><div class="DeployYosoWrap"><div class="DeployBox">' + "".join('<div class="DeployInBox"><div class="Shaban_InBox"><span class="Shaban_Num">'+str(n)+'</span></div></div>' + ('<div class="DeployInBox"><div class="Shaban_InBox"><span class="WakuSeparat"></span></div></div>' if n in (2,5) else "") for n in range(1,8)) + "</div></div></div>"
        assert inspect(nk, {"size":7})["netkeirinGroupCandidate"] == [[1,2],[3,4,5],[6,7]]
        assert inspect(nk.replace(">7<", ">6<"), {"size":7})["netkeirinGroupCandidate"] is None
        print("SELF_TEST_OK")
        return
    lines = load("verified-line-snapshots-feed-v1.json")
    q = queue(load("verified-results-feed-v1.json"),lines,a.limit,a.offset,load("verified-rider-results-feed-v1.json"))
    slugs = venue_slugs(lines)
    meetings = meeting_prefixes(lines)
    blocked_hosts = set()
    for c in q["candidates"]:
        urls = source_urls(c,slugs,meetings)
        if not urls:
            print(json.dumps({"key":c["key"],"state":"NO_KNOWN_URL_PATTERN","formalPass":False}),flush=True)
        for url in urls:
            host = urlsplit(url).netloc
            record = {"key":c["key"],"candidateUrl":url,"formalPass":False}
            if host in blocked_hosts:
                record.update(state="HOLD",reason="Host policy unavailable earlier in this run")
                print(json.dumps(record,ensure_ascii=False),flush=True)
                continue
            try:
                require_robots_access(url,host,AGENT)
            except (requests.RequestException,ValueError) as e:
                if "prohibit" not in str(e):
                    blocked_hosts.add(host)
                record.update(state="HOLD",reason=str(e))
                print(json.dumps(record,ensure_ascii=False),flush=True)
                continue
            try:
                with requests.get(url,headers={"User-Agent":AGENT},timeout=15,allow_redirects=False,stream=True) as r:
                    if r.status_code != 200:
                        raise ValueError(f"HTTP {r.status_code}")
                    data = bytearray()
                    for chunk in r.iter_content(65536):
                        data.extend(chunk)
                        if len(data)>3000000:
                            raise ValueError("HTML too large")
                    record.update(inspect(bytes(data), c))
                    record.update(state="HTML_RETRIEVED_UNVERIFIED",sha256=hashlib.sha256(data).hexdigest(),retrievedAt=datetime.now(timezone.utc).isoformat())
            except (requests.RequestException,ValueError) as e:
                record.update(state="HOLD",reason=str(e))
            time.sleep(1)
            print(json.dumps(record,ensure_ascii=False),flush=True)
            if record.get("gambooGroupCandidate") and record.get("riderTableObservations"):
                break

if __name__ == "__main__":
    main()
