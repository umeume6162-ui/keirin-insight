#!/usr/bin/env python3
"""One-off, read-only published result HTML structure research.

Never saves rider information or results. Checks per-URL robots restrictions,
finite HTTPS domain allowlist, response size and short timeouts.
"""
import json
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

AGENT = "KEIRIN-INSIGHT-Research/1.0 (one public layout check)"
URLS = (
    ("yenjoy", "https://www.yen-joy.net/kaisai/race/result/202611/61/20261123/20261123"),
    ("kdreams", "https://keirin.kdreams.jp/tamano/racedetail/6120261123010001/?pageType=showResult"),
)

def inspect(label, url):
    host = urlsplit(url).netloc
    if urlsplit(url).scheme != "https" or host not in {"www.yen-joy.net", "keirin.kdreams.jp"}:
        raise ValueError("Unapproved HTTPS host")
    result = {"source": label, "status": "UNKNOWN"}
    try:
        robots = requests.get("https://" + host + "/robots.txt",
                              headers={"User-Agent": AGENT}, timeout=12)
        result["robotsStatus"] = robots.status_code
        if robots.status_code == 200:
            parser = RobotFileParser()
            parser.parse(robots.text.splitlines())
            if not parser.can_fetch(AGENT, url):
                result["status"] = "ROBOTS_BLOCKED"
                return result
        elif robots.status_code not in (404, 410):
            result["status"] = "ROBOTS_UNKNOWN"
            return result
        page = requests.get(url, headers={"User-Agent": AGENT}, timeout=15)
        result["httpStatus"] = page.status_code
        if page.status_code != 200:
            result["status"] = "HTTP_UNAVAILABLE"
            return result
        if len(page.content) > 3000000:
            result["status"] = "TOO_LARGE"
            return result
        soup = BeautifulSoup(page.text, "html.parser")
        headings = []
        for tag in soup.select("h1,h2,h3,h4")[:18]:
            t = tag.get_text(" ", strip=True)
            if any(word in t for word in ("結果", "1R", "1Ｒ", "着順", "レース", "玉野")):
                headings.append(t[:45])
        tables = []
        for table in soup.select("table")[:20]:
            trs = table.find_all("tr")
            if len(trs) < 3:
                continue
            headers = [t.get_text(" ", strip=True)[:30]
                       for t in trs[0].find_all(["th", "td"], recursive=False)]
            if not headers:
                headers = [t.get_text(" ", strip=True)[:30]
                           for t in trs[1].find_all(["th", "td"], recursive=False)]
            tables.append({"rows": len(trs), "columns": len(headers),
                           "headers": headers[:15]})
        result.update(status="HTML_OBSERVED", headings=headings[:12],
                      tableCount=len(soup.select("table")), tables=tables[:12],
                      resultHeadings=sum("結果" in h for h in headings))
        return result
    except requests.exceptions.RequestException as exc:
        result["status"] = "NETWORK_UNAVAILABLE"
        result["errorClass"] = type(exc).__name__
        return result

if __name__ == "__main__":
    for label, url in URLS:
        print("PUBLIC_RESULT_PROBE " + json.dumps(inspect(label, url), ensure_ascii=False))
