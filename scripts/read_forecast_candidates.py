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

def inspect(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    # Diagnostic excerpts only; never infer line boundaries from whitespace.
    excerpts = []
    for node in soup.find_all(string=re.compile("並び予想|ライン予想|並び想定")):
        parent = node.parent
        if parent.name in ("script", "style"):
            continue
        block = parent.parent or parent
        value = block.get_text(" ", strip=True)
        if value not in excerpts:
            excerpts.append(value[:1200])
        if len(excerpts) >= 5:
            break
    return {"title": title, "forecastLabelContexts": excerpts}

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
        print("SELF_TEST_OK")
        return
    lines = load("verified-line-snapshots-feed-v1.json")
    q = queue(load("verified-results-feed-v1.json"),lines,a.limit,a.offset,load("verified-rider-results-feed-v1.json"))
    slugs = venue_slugs(lines)
    for c in q["candidates"]:
        url = candidate_url(c,slugs)
        record = {"key":c["key"],"candidateUrl":url,"formalPass":False}
        if not url:
            record["state"] = "NO_KNOWN_URL_PATTERN"
        else:
            try:
                require_robots_access(url, HOST, AGENT)
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

if __name__ == "__main__":
    main()
