#!/usr/bin/env python3
"""Idempotent GitHub -> Google Sheets daily race intake.

Input: JSON object with entries[] and results[]. Only explicit validated records are
written. Default --dry-run. No deleting rows or modifying legacy GAS/V99 tabs.
"""
import argparse
import json
import os
import re
import sys
import requests
from datetime import datetime
from pathlib import Path

SHEET_ID = "1gCe5q5STYH0T8XKqxJbVawB0Cl8TPsCISFJiRUdA02M"
CONFIG = {
    "entries": (
        "KI｜日次出走表",
        ["date","trackCode","track","race","className","number","name","prefecture",
         "period","preRaceLine","sourceUrl","capturedAt","state","raceKey","sourceId"]),
    "results": (
        "KI｜日次結果",
        ["date","trackCode","track","race","className","number","name","prefecture",
         "period","finish","method","exception","sourceUrl","capturedAt","raceKey"]),
}
HEADERS = {
    "entries": ["開催日","場コード","競輪場","R","級班","車番","選手名","府県","期別",
                "発走前ライン","元URL","取得日時JST","収集状態","レースキー","ソースID"],
    "results": ["開催日","場コード","競輪場","R","級班","車番","選手名","府県","期別",
                "着順原文","決まり手","個人状況・例外","元URL","取得日時JST","レースキー"],
}
REQUIRED = ["date","trackCode","track","race","className","number","name","sourceUrl"]
DAY = re.compile(r"^20\d\d-\d\d-\d\d$")
SOURCE = re.compile(r"^https://[^/\s]+/.+")
ALLOWED_STATUS = {"欠車","取消","失格","落車棄権","途中棄権","棄権"}

def normalize_record(kind, record):
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    for k in REQUIRED:
        if str(record.get(k, "")).strip() == "":
            raise ValueError("missing required " + kind + " field " + k)
    date = str(record["date"]).strip()
    if not DAY.fullmatch(date):
        raise ValueError("bad date: " + date)
    datetime.strptime(date, "%Y-%m-%d")
    track_code = str(record["trackCode"]).strip()
    if not track_code.isdigit() or not 1 <= int(track_code) <= 99:
        raise ValueError("bad track code")
    track_code = track_code.zfill(2)
    race = int(record["race"])
    number = int(record["number"])
    if not 1 <= race <= 12 or not 1 <= number <= 9:
        raise ValueError("race/car out of range")
    source = str(record["sourceUrl"]).strip()
    if not SOURCE.fullmatch(source):
        raise ValueError("source URL missing or invalid")
    if kind == "results":
        finish = str(record.get("finish") or "").strip()
        if finish and not (finish.isdigit() or finish in ALLOWED_STATUS):
            raise ValueError("unknown finish state: " + finish)
        if not finish:
            raise ValueError("result finish/status missing")
    vals = dict(record)
    vals.update(date=date, trackCode=track_code, race=str(race), number=str(number),
                raceKey=f"{date}|{track_code}|{race}")
    return [str(vals.get(key) if vals.get(key) is not None else "") for key in CONFIG[kind][1]]

def prepare(input_data):
    if not isinstance(input_data, dict):
        raise ValueError("expected JSON object")
    if set(input_data) - {"entries","results","sourceNote"}:
        raise ValueError("unexpected input keys")
    output = {}
    for kind in CONFIG:
        rows = input_data.get(kind, [])
        if not isinstance(rows, list):
            raise ValueError(kind + " must be a list")
        keyed = {}
        for row in rows:
            values = normalize_record(kind, row)
            key = values[13 if kind == "entries" else 14] + "|" + values[5]
            if key in keyed and keyed[key] != values:
                raise ValueError("conflicting input duplicate: " + key)
            keyed[key] = values
        output[kind] = keyed
    return output

def remote_client():
    import google.auth.transport.requests
    from google.oauth2 import service_account
    import requests
    secret = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not secret:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not set")
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(secret), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    credentials.refresh(google.auth.transport.requests.Request())
    return requests.Session(), credentials.token

def ensure_write_allowed(response):
    """Explain Sheets write denials without exposing credentials."""
    if response.status_code == 403:
        raise PermissionError(
            "Google Sheets HTTP 403 on write. Check whether the private GitHub "
            "service account has Editor permission to this spreadsheet and "
            "whether the Sheets API is enabled. Do not print credentials "
            "or change public link permissions."
        )
    response.raise_for_status()


def verify_writer():
    """Permission probe: rewrite the existing daily header with identical text.

    Never creates a race, changes a rider row, or reveals the credential.
    Requires live Sheets write permission and confirms the cell on re-read.
    """
    session, token = remote_client()
    import urllib.parse
    url = ("https://sheets.googleapis.com/v4/spreadsheets/" + SHEET_ID +
           "/values/" + urllib.parse.quote("'KI｜日次出走表'!A1", safe=""))
    headers = {"Authorization": "Bearer " + token}
    first = session.get(url, headers=headers, timeout=30)
    first.raise_for_status()
    if first.json().get("values") != [["開催日"]]:
        raise ValueError("Daily intake A1 header mismatch; write probe aborted")
    response = session.put(
        url, headers={**headers, "Content-Type": "application/json"},
        params={"valueInputOption": "RAW"},
        json={"range": "'KI｜日次出走表'!A1", "majorDimension": "ROWS",
              "values": [["開催日"]]},
        timeout=30
    )
    ensure_write_allowed(response)
    confirm = session.get(url, headers=headers, timeout=30)
    confirm.raise_for_status()
    if confirm.json().get("values") != [["開催日"]]:
        raise ValueError("Daily intake A1 re-read differs; probe unsuccessful")
    return {"status": "SHEETS_WRITER_VERIFIED",
            "scope": "daily entry A1 unchanged", "secret_exposed": False}


def apply(input_data, dry_run=True):
    records = prepare(input_data)
    if not any(records.values()):
        return {"entries": 0,"results": 0,"writes": 0,"status": "no records"}
    session, token = remote_client()
    base = "https://sheets.googleapis.com/v4/spreadsheets/" + SHEET_ID + "/values"
    headers = {"Authorization": "Bearer " + token}
    read_ranges = ["'" + CONFIG[k][0] + "'!A1:O10000" for k in CONFIG]
    resp = session.get(base + ":batchGet", params=[("ranges", x) for x in read_ranges],
                       headers=headers, timeout=40)
    resp.raise_for_status()
    remote = resp.json().get("valueRanges", [])
    if len(remote) != 2:
        raise RuntimeError("Unexpected sheet read count")
    planned = []
    summary = {}
    for i, kind in enumerate(CONFIG):
        name = CONFIG[kind][0]
        current = remote[i].get("values", [])
        if not current or current[0] != HEADERS[kind]:
            raise ValueError("Refuse write: sheet header mismatch " + name)
        original = {}
        for row_number, row in enumerate(current[1:], start=2):
            cells = ["" if x is None else str(x) for x in row] + [""] * max(0, 15 - len(row))
            if not cells[0]:
                continue
            key = cells[13 if kind == "entries" else 14] + "|" + cells[5]
            if key in original:
                raise ValueError("Duplicate existing key: " + key)
            original[key] = (row_number, cells)
        inserts, updates = [], []
        for key, values in records[kind].items():
            found = original.get(key)
            if found is None:
                inserts.append(values)
                continue
            row_number, previous = found
            # Do not silently erase existing attributes when new source omits them.
            # Reject contradictory rider/meeting identity rather than silently
            # modifying an already recorded car-number observation.
            for j in (0, 1, 2, 3, 4, 5, 6, 7, 8):
                if previous[j] and values[j] and previous[j] != values[j]:
                    raise ValueError(
                        "Identity/meeting conflict for " + key +
                        " at column " + str(j + 1) + "; review source"
                    )
            merged = [new if new != "" else old for old,new in zip(previous, values)]
            # A repeated identical observation should not update only its capture clock.
            time_idx = 11 if kind == "entries" else 13
            if all(previous[j] == merged[j] for j in range(15) if j != time_idx):
                merged[time_idx] = previous[time_idx]
            if previous != merged:
                updates.append((row_number, merged))
        for row_number, values in updates:
            planned.append({"range": "'" + name + "'!A" + str(row_number) + ":O" + str(row_number),
                            "values":[values]})
        # Append is handled in a separate request, since updates must not rely on row indices.
        summary[kind] = {"new":len(inserts),"changed":len(updates),"unchanged":len(records[kind])-len(inserts)-len(updates)}
        summary[kind]["append"] = inserts
    if dry_run:
        return {"status":"DRY_RUN","summary":{k:{p:v for p,v in s.items() if p!="append"} for k,s in summary.items()},
                "planned_updates":len(planned)}
    if planned:
        resp = session.post(base + ":batchUpdate", headers={**headers,"Content-Type":"application/json"},
                            json={"valueInputOption":"RAW","data":planned}, timeout=45)
        ensure_write_allowed(resp)
    for kind in CONFIG:
        new = summary[kind]["append"]
        if not new:
            continue
        name = CONFIG[kind][0]
        resp = session.post(base + "/" + requests.utils.quote("'" + name + "'!A:O",safe="!:") + ":append",
                            headers={**headers,"Content-Type":"application/json"},
                            params={"valueInputOption":"RAW","insertDataOption":"INSERT_ROWS"},
                            json={"values":new}, timeout=45)
        ensure_write_allowed(resp)
    return {"status":"SAVED","summary":{k:{p:v for p,v in s.items() if p!="append"} for k,s in summary.items()}}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input")
    p.add_argument("--verify-write-access", action="store_true", help="Verify editor permission by idempotently rewriting daily A1 header")
    p.add_argument("--apply", action="store_true", help="Write to Sheets; default is dry run")
    p.add_argument("--validate-only", action="store_true", help="Validate input without credentials or network")
    args = p.parse_args()
    if args.verify_write_access:
        if args.input or args.apply or args.validate_only:
            p.error("--verify-write-access must be used alone")
        print(json.dumps(verify_writer(), ensure_ascii=False))
        return
    if not args.input:
        p.error("--input required unless --verify-write-access")
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.validate_only:
        if args.apply:
            raise ValueError("--validate-only cannot be used with --apply")
        normalized = prepare(data)
        print(json.dumps({"status":"VALID","entries":len(normalized["entries"]),
                          "results":len(normalized["results"])}, ensure_ascii=False))
    else:
        print(json.dumps(apply(data, dry_run=not args.apply), ensure_ascii=False))
if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ABORT: " + str(exc), file=sys.stderr)
        sys.exit(1)
