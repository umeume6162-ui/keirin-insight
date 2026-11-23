#!/usr/bin/env node
'use strict';
// Offline proof regression: transform ONE already verified 7-car K-Dreams race
// into a Chariloto single-source example. This DOES NOT publish that race.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),cp=require('node:child_process'),assert=require('node:assert/strict'),vm=require('node:vm');
const read=n=>JSON.parse(fs.readFileSync(n,'utf8'));
const files=['verified-rider-ids-feed-v1.json','comparison-races-v1.json','verified-results-feed-v1.json','verified-rider-results-feed-v1.json','verified-line-snapshots-feed-v1.json'];
const [ids,comparison,races,riders,lines]=files.map(read);
// Isolate the fallback-result contract from unrelated historical rider-ID records.
ids.riders=ids.riders.slice(0,1);ids.summary.rows=ids.riders.length;
const record=races.races.find(r=>r.officialVerification?.method==='kdreams_single_source_verified'&&r.size===7);
assert.ok(record,'known verified source fixture');
const source='https://www.chariloto.com/keirin/results/75/2026-10-05/';
const key=record.key,old=record.officialVerification;
record.officialVerification={status:'verified',source,method:'fallback_source_verified',matchingSources:[source],fields:old.fields,
sourceProof:{kind:'live_html',sourceTier:'other_media',retrievedDate:'2026-11-24',
evidenceRef:'TEST-ONLY-READONLY-ALL-7-CAR-OBSERVATION',runUrl:'https://github.com/umeume6162-ui/keirin-insight/actions/runs/45218073230'}};
const col=Object.fromEntries(riders.columns.map((s,i)=>[s,i]));
const rows=riders.rows.filter(r=>[r[col.date],String(r[col.trackCode]),Number(r[col.race])].join('|')===key);
assert.equal(rows.length,7);rows.forEach(r=>{r[col.sourceUrl]=source});
const src=fs.readFileSync('verified-publication-guard-v138.js','utf8');
const fakeWindow={fetch:async()=>{}};
vm.runInNewContext(src,{window:fakeWindow,URL,Date,Error,Set,Map,Number,String,RegExp,Array,Promise,AbortController,Response,location:{href:'https://example.test/'}});
assert.equal(typeof fakeWindow.KIVerified.validate,'function');
function browserVerify(){fakeWindow.KIVerified.validate(races,riders,ids,lines)}
function offlineVerify(expectSuccess){const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ki-fallback-'));try{[ids,comparison,races,riders,lines].forEach((o,i)=>fs.writeFileSync(path.join(tmp,files[i]),JSON.stringify(o)));const check=cp.spawnSync(process.execPath,[path.resolve('tools/check_publication_completeness.cjs')],{cwd:tmp,encoding:'utf8'});if(expectSuccess)assert.equal(check.status,0,check.stderr);else assert.notEqual(check.status,0,'tampered input must be rejected')}finally{fs.rmSync(tmp,{recursive:true,force:true})}}
browserVerify();offlineVerify(true);
const original=rows[0][col.sourceUrl];rows[0][col.sourceUrl]='https://evil.example/unsupported';
assert.throws(browserVerify,/掲載検査/);offlineVerify(false);
rows[0][col.sourceUrl]=original;
const proof=record.officialVerification.sourceProof;const originalTier=proof.sourceTier;proof.sourceTier='venue_official';
assert.throws(browserVerify,/掲載検査/);offlineVerify(false);
proof.sourceTier=originalTier;
browserVerify();offlineVerify(true);
console.log('FALLBACK_PUBLICATION_TEST_OK: 7-car single source accepted, wrong row URL and source tier rejected; original data untouched');
