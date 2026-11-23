#!/usr/bin/env python3
"""One-off read-only public keirin source capability probe.

Does not persist HTML, racer details, or any Sheets data. Respects robots.txt,
checks one named race page per host, and prints only aggregate page-shape facts.
"""
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

UA="KEIRIN-INSIGHT-Research/1.0 (single-race public page assessment)"
SOURCES={
  "kdreams":"https://keirin.kdreams.jp/seibuen/racedetail/2620261123010001/",
  "tospo":"https://keirin.tokyo-sports.co.jp/list/race/20261122_31332",
  "gendai":"https://keirin-autorace.nikkan-gendai.com/Keirin/StartingList?date=20261123&placeCode=26&raceNo=1",
}
def run(name,url):
    host=urlsplit(url)
    try:
        robot=requests.get(f"{host.scheme}://{host.netloc}/robots.txt",timeout=12,headers={"User-Agent":UA})
        if robot.status_code == 200:
            p=RobotFileParser()
            p.parse(robot.text.splitlines())
            if not p.can_fetch(UA,url):
                return {"source":name,"status":"robots_disallow"}
        elif robot.status_code not in (404,410):
            return {"source":name,"status":"robots_unknown","http":robot.status_code}
        r=requests.get(url,headers={"User-Agent":UA},timeout=20)
        if r.status_code!=200:
            return {"source":name,"status":"http_error","http":r.status_code}
        if len(r.content)>3_000_000:
            return {"source":name,"status":"too_large"}
        soup=BeautifulSoup(r.text,"html.parser")
        txt=soup.get_text(" ",strip=True)
        headings=[x.get_text(" ",strip=True).replace(" ","")[:25] for x in soup.select("th")[:12]]
        return {"source":name,"status":"page_read","bytes":len(r.content),
                "textChars":len(txt),"tableCount":len(soup.select("table")),
                "raceTextPresent":("西武園" in txt),"riderMarkerPresent":("山崎" in txt),
                "nameHeadingPresent":("選手名" in txt),"headings":headings}
    except requests.RequestException as e:
        return {"source":name,"status":"network_error","type":type(e).__name__}
if __name__=="__main__":
    print("SOURCE_SHAPES "+json.dumps([run(n,u) for n,u in SOURCES.items()],ensure_ascii=False))
