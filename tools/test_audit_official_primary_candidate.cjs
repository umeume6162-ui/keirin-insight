#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {audit}=require('./audit_official_primary_candidate.cjs');
const candidate={raceKey:'2026-11-20|22|2',results:[
 {car:2,name:'阿部 凪汰',finishRaw:'1',finish:1,lapSeconds:10.6,marginRaw:'',winningMethodRaw:'逃',sbRaw:'B',exceptionRaw:''},
 {car:6,name:'右近 陸人',finishRaw:'2',finish:2,lapSeconds:10.5,marginRaw:'1/2車身',winningMethodRaw:'ク',sbRaw:'S',exceptionRaw:''}
]};
const fixture={schema:'ki-official-primary-transcription-v1',raceKey:candidate.raceKey,issuer:'JKA_KEIRIN_JP',sourceUrl:'https://keirin.jp/pc/racelist',retrievedDateJST:'2026-11-22',retrievalMethod:'verified-original-snapshot',originalRecordVerified:true,exampleOnly:true,results:JSON.parse(JSON.stringify(candidate.results))};
// Even perfectly matching fabricated data must NEVER pass the official evidence gate.
const fake=audit(candidate,fixture);
assert.equal(fake.publicationPassed,false);assert.equal(fake.status,'NOT_READY');assert.ok(fake.errors.some(x=>x.includes('synthetic')));
const absent=audit(candidate,{});
assert.equal(absent.publicationPassed,false);assert.equal(absent.status,'NOT_READY');
assert.ok(absent.errors.some(x=>x.includes('official full result rows not supplied')));
const mismatch=JSON.parse(JSON.stringify(fixture));delete mismatch.exampleOnly;
mismatch.results[0].finishRaw='2';mismatch.results[0].finish=2;
const bad=audit(candidate,mismatch);
assert.equal(bad.status,'NOT_READY');assert.ok(bad.unresolved.some(x=>x.field==='finish'));
const blank=JSON.parse(JSON.stringify(fixture));delete blank.exampleOnly;
blank.results[1].sbRaw='';
const missing=audit(candidate,blank);
assert.ok(missing.unresolved.some(x=>x.field==='sbRaw'));
assert.equal(missing.publicationPassed,false);
const normalized=JSON.parse(JSON.stringify(fixture));delete normalized.exampleOnly;
normalized.results[0].winningMethodRaw='逃げ';
normalized.results[1].winningMethodRaw='マーク';
const comparison=audit(candidate,normalized);
assert.equal(comparison.errors.length,0);assert.equal(comparison.unresolved.length,0);
assert.equal(comparison.publicationPassed,false);
assert.equal(comparison.status,'FIELD_MATCH_ONLY_STILL_REQUIRES_SECONDARY_CORROBORATION_AND_PUBLICATION_GATE');
// The last fixture is SYNTHETIC TEST DATA. This test does NOT establish a real official original.
console.log('OK: official-primary offline comparison rejects missing/synthetic/contradictory evidence, never promotes PASS');
