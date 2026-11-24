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
    return urls

def inspect(html):
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
        if not any("選手名" in h.replace(" ", "") for h in heads):
            continue
        rows = []
        for tr in table.find_all("tr")[:20]:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th","td"], recursive=False)]
            if cells:
                rows.append(cells)
        tables.append({"headers":heads,"rows":rows})
        if len(tables) >= 3:
            break
    return {"title": title, "forecastLabelContexts": excerpts,
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
        assert len(source_urls({"key":"2026-01-03|85|6"},slugs,meetings)) == 1
        observed = inspect('<div><b>並び予想</b><span class="test-group">①②</span><span>③</span></div><table><tr><th>選手名</th></tr><tr><td>試験選手</td></tr></table>')
        assert 'class="test-group"' in observed["forecastElementHtml"][0]
        assert observed["riderTableObservations"][0]["rows"][1] == ["試験選手"]
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
                    record.update(inspect(bytes(data)))
                    record.update(state="HTML_RETRIEVED_UNVERIFIED",sha256=hashlib.sha256(data).hexdigest(),retrievedAt=datetime.now(timezone.utc).isoformat())
            except (requests.RequestException,ValueError) as e:
                record.update(state="HOLD",reason=str(e))
            time.sleep(1)
            print(json.dumps(record,ensure_ascii=False),flush=True)
            if record.get("forecastLabelContexts"):
                break

if __name__ == "__main__":
    main()
