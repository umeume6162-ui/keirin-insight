#!/usr/bin/env python3
"""Read-only V99 -> public snapshots. No changes to the Google spreadsheet."""
import argparse
import csv
import io
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SHEET_ID = '1gCe5q5STYH0T8XKqxJbVawB0Cl8TPsCISFJiRUdA02M'
SHEET_NAME = 'V99選手結果蓄積'
HEADERS = ['開催日','競輪場','場コード','グレード','R','レース級','着順原文','車番','選手名','年齢','府県','期別','選手級班','着差','上り','決まり手','S/B','個人状況','結果分類','正式選手ID','照合状態','出典URL','取得日時']
RIDER_COLUMNS = ['name','prefecture','period','date','track','trackCode','race','finishRaw','number','riderClass','winningMethod','sourceUrl']


def fetch_sheet(credentials_json):
    """Google Sheets API read-only; never uses public/anonymous sheet publication."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    try:
        info = json.loads(credentials_json)
    except json.JSONDecodeError as e:
        raise ValueError(f'Google credential JSON format error: {e.msg} (line {e.lineno}, column {e.colno}). Check GitHub Secret GOOGLE_SERVICE_ACCOUNT_JSON; do not print its contents.') from None
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    session = AuthorizedSession(creds)
    url = 'https://sheets.googleapis.com/v4/spreadsheets/' + SHEET_ID + '/values/' + SHEET_NAME + '!A1:W'
    response = session.get(url, timeout=45)
    response.raise_for_status()
    return response.json()['values']


def cleaned(x):
    return str(x or '').strip()


def normalize(rows):
    if not rows or [cleaned(v) for v in rows[0]] != HEADERS:
        raise ValueError('V99 header mismatch: abort without publishing')
    # An exact row key prevents accidentally double-counting script retries.
    candidates=[]
    seen=set()
    for i, values in enumerate(rows[1:], 2):
        values = list(values) + [''] * (len(HEADERS)-len(values))
        if not any(cleaned(v) for v in values):
            continue
        if len(values) > len(HEADERS):
            raise ValueError(f'Unexpected extra columns on row {i}')
        d = dict(zip(HEADERS, (cleaned(x) for x in values)))
        date=d['開催日']; track=d['競輪場']; code=d['場コード']; race=d['R']; num=d['車番']
        if not re.fullmatch(r'20\d\d-\d\d-\d\d',date):
            raise ValueError(f'Bad date row {i}: {date}')
        if not (track and code.isdigit() and race.isdigit() and num.isdigit() and d['選手名']):
            raise ValueError(f'Missing required race/rider data on row {i}')
        if not (1 <= int(race) <= 12 and 1 <= int(num) <= 9):
            raise ValueError(f'Out-of-bounds race or number row {i}')
        rowkey=(date,code,int(race),int(num))
        if rowkey in seen:
            raise ValueError(f'Duplicate rider number in race: {rowkey}')
        seen.add(rowkey)
        candidates.append(d)
    if not candidates: raise ValueError('No rider results')
    return candidates


def grade_of(records):
    rider_classes={x['選手級班'].upper() for x in records if x['選手級班']}
    grade_raw={x['レース級'].upper() for x in records}
    if any(x.startswith('L') for x in rider_classes) or 'L' in grade_raw:
        return 'ガールズ'
    if any(x.startswith('S') for x in rider_classes) or 'S' in grade_raw:
        return 'S級'
    if rider_classes and all(x=='A3' for x in rider_classes):
        return 'A3'
    if rider_classes and all(x in ('A1','A2') for x in rider_classes):
        return 'A1/A2'
    raise ValueError(f'A grade classification ambiguous: {sorted(rider_classes)}')


def construct(data, date):
    grouped={}
    for d in data:
        k=(d['開催日'],d['場コード'],int(d['R']))
        grouped.setdefault(k,[]).append(d)
    races=[]
    for k, rr in grouped.items():
        if len(rr)>9 or len(rr)<4: raise ValueError(f'Unexpected race size {k}: {len(rr)}')
        g=grade_of(rr)
        if len({x['競輪場'] for x in rr})!=1: raise ValueError(f'Track mismatch for {k}')
        sources={x['出典URL'] for x in rr if x['出典URL']}
        if len(sources)>1: raise ValueError(f'Conflicting result source for {k}')
        races.append(dict(key='|'.join(map(str,k)),date=k[0],track=rr[0]['競輪場'],track_code=k[1],race=k[2],grade=g,size=len(rr),source=next(iter(sources),''),non_numeric=sum(not re.fullmatch(r'\d+',x['着順原文']) for x in rr)))
    races.sort(key=lambda x:(x['date'],int(x['track_code']),x['race']),reverse=True)
    summary=Counter(x['grade'] for x in races)
    latest=max(x['date'] for x in races)
    result={'schema':'ki-public-results-index-v1','origin_sheet':SHEET_NAME,'source_snapshot_date':date,'latest_race_date':latest,'official_result_independent_audit':'incomplete','notes':'Read-only Google Sheets V99 snapshot. Not live prediction data or proof of official validation.','summary':{'races':len(races),'rider_rows':len(data),'by_grade':dict(summary)},'races':races}
    # Preserve the v10.8 row schema verbatim for existing pages.
    rider_rows=[[x[k] for k in ['選手名','府県','期別','開催日','競輪場','場コード','R','着順原文','車番','選手級班','決まり手','出典URL']] for x in data]
    ident={(x[0].replace(' ', '').replace('　',''),x[1],x[2]) for x in rider_rows}
    rider={'schema':'ki-rider-results-v1','snapshotDate':date,'latestEventDate':latest,'sourceTab':SHEET_NAME,'verificationNote':'収録データの集計。公式結果との全件独立照合未完了。公式選手IDは公開データに含めていない。','columns':RIDER_COLUMNS,'summary':{'rows':len(rider_rows),'riders':len(ident),'races':len(races)},'rows':rider_rows}
    return result,rider


def validate_against_existing(result,rider,root,allow_drop=False):
    if result['summary']['races'] != rider['summary']['races'] or result['summary']['rider_rows'] != rider['summary']['rows']:
        raise ValueError('Public feed cross-check mismatch')
    for path,newcount in [('results-feed-v1.json',result['summary']['races']),('rider-results-feed-v1.json',rider['summary']['rows'])]:
        p=root/path
        if not p.is_file():
            raise ValueError(f'No baseline feed {path}: refuse first write without baseline')
        old=json.loads(p.read_text(encoding='utf-8'))
        oldcount = old['summary']['races'] if path == 'results-feed-v1.json' else old['summary']['rows']
        if not allow_drop and newcount<oldcount:
            raise ValueError(f'Count decreased for {path}: {oldcount} -> {newcount}. Review source, not auto-overwrite.')
        if result['latest_race_date'] < (old.get('latest_race_date') or old.get('latestEventDate') or ''):
            raise ValueError('Newest race date regressed')
    # Existing row identities must remain: append-only auto-publishing.
    prev=json.loads((root/'rider-results-feed-v1.json').read_text(encoding='utf-8'))
    previous={tuple(x) for x in prev['rows']}
    now={tuple(x) for x in rider['rows']}
    if not allow_drop and not previous.issubset(now):
        raise ValueError(f'{len(previous-now)} prior rows changed/disappeared: manual review required')
    # Do not publish invalid or empty track/date or unverified official ID.
    if len(now) != len(rider['rows']): raise ValueError('Duplicate full rider rows')


def write_atomic(path, payload):
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n'
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f:
        f.write(data); temp=f.name
    os.replace(temp,path)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--fixtures',help='Local CSV test file (not for scheduled publishing)')
    parser.add_argument('--root',default='.')
    parser.add_argument('--allow-rebuild',action='store_true',help='Manual repair only, not used by automation')
    args=parser.parse_args()
    root=Path(args.root)
    if args.fixtures:
        with open(args.fixtures,encoding='utf-8-sig',newline='') as f: values=list(csv.reader(f))
    else:
        secret=os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON','')
        if not secret: raise ValueError('GOOGLE_SERVICE_ACCOUNT_JSON is missing; no writes performed')
        values=fetch_sheet(secret)
    data=normalize(values)
    stamp=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    index,rider=construct(data,stamp)
    validate_against_existing(index,rider,root,allow_drop=args.allow_rebuild)
    # Operational diagnostics: distinguish a healthy publish from stale upstream V99 data.
    previous_path=root/'rider-results-feed-v1.json'
    if previous_path.exists():
        previous=json.loads(previous_path.read_text(encoding='utf-8'))
        old_rows=len(previous.get('rows',[]))
        old_latest=previous.get('latestEventDate','')
        delta=len(rider['rows'])-old_rows
        print(f'FEED_AUDIT rows_previous={old_rows} rows_current={len(rider["rows"])} delta={delta} latest_previous={old_latest} latest_current={index["latest_race_date"]}')
        if delta == 0:
            print('WARNING: V99 has no new rider rows relative to the published feed. Check upstream GAS collection and V99 append logs; JSON publishing alone cannot add missing results.',file=sys.stderr)
        if index['latest_race_date']==old_latest:
            print('WARNING: Latest race date has not advanced. Verify source collection settings and trigger executions.',file=sys.stderr)
    latest_date=datetime.strptime(index['latest_race_date'],'%Y-%m-%d').date()
    lag=(datetime.now(timezone.utc).date()-latest_date).days
    print(f'FEED_AUDIT latest_race_lag_days={lag}')
    if lag>7:
        print(f'WARNING: Latest V99 race is {lag} days old; collection freshness needs investigation.',file=sys.stderr)
    # Stage both serialized feeds before replacing either baseline.
    # GitHub Actions will only commit if this entire step succeeds.
    index_json=json.dumps(index,ensure_ascii=False,separators=(',',':'))+'\n'
    rider_json=json.dumps(rider,ensure_ascii=False,separators=(',',':'))+'\n'
    json.loads(index_json); json.loads(rider_json)
    write_atomic(root/'results-feed-v1.json',index)
    write_atomic(root/'rider-results-feed-v1.json',rider)
    print(f'Validated: {index["summary"]["races"]} races, {rider["summary"]["rows"]} rows, {rider["summary"]["riders"]} riders; latest {index["latest_race_date"]}')


if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'ABORT (public JSON unchanged): {e}',file=sys.stderr)
        sys.exit(1)
