#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {auditAll,inspectSourceFirst}=require('./audit_all_acquired_races.cjs');
const base={raceKey:'2026-11-20|22|1',race:{venue:'前橋'},originalEntries:[{car:1,name:'甲'},{car:2,name:'乙'},{car:3,name:'丙'},{car:4,name:'丁'},{car:5,name:'戊'},{car:6,name:'己'},{car:7,name:'庚'}],preRaceFormation:{groups:[[1,2,3,4,5,6,7]]},results:Array.from({length:7},(_,i)=>({car:i+1,finish:i+1,finishRaw:String(i+1),name:'選手'+i,lapSeconds:11.5+i/10,marginRaw:i===0?'':'1車身',winningMethodRaw:i===0?'逃':'',sbRaw:i===0?'B':'',exceptionRaw:''})),reconciliation:{revisedStartCardSource:null},resultUrls:['https://a.example/result','https://b.example/result']};
const a=inspectSourceFirst(base);
assert.equal(a.documentedRows,7);assert.equal(a.numericFinishers,7);assert.equal(a.publicationPassed,false);
assert.ok(a.blockers.includes('OFFICIAL_ORGANIZER_PRIMARY_NOT_CAPTURED'));
const missing=JSON.parse(JSON.stringify(base));missing.originalEntries[6].car=8;
assert.ok(inspectSourceFirst(missing).blockers.includes('ENTRY_RESULT_CAR_MISMATCH_CHECK_OFFICIAL_WITHDRAWALS'));
const blank=JSON.parse(JSON.stringify(base));blank.results[6].lapSeconds=null;
assert.ok(inspectSourceFirst(blank).blockers.some(s=>s.startsWith('NUMERIC_FINISHER_LAP_NOT_DISPLAYED')));
const exceptional=JSON.parse(JSON.stringify(base));exceptional.results[6].finishRaw='落';exceptional.results[6].finish=null;exceptional.results[6].exceptionRaw='落';exceptional.results[6].lapSeconds=null;
const e=inspectSourceFirst(exceptional);assert.equal(e.numericFinishers,6);assert.equal(e.exceptionRows.length,1);
const comparison={races:[{key:'2026-10-05|75|1',track:'松山',finishers:Array.from({length:7},(_,i)=>({number:i+1,finish:String(i+1)})),formation:{groups:[[1,2,3,4,5,6,7]]},resultSourcePair:['https://a.example/','https://b.example/']}]};
const sum=auditAll([base],comparison);assert.equal(sum.summary.allRaces,2);assert.equal(sum.summary.resultRows,14);assert.equal(sum.summary.formalPass,0);
assert.throws(()=>auditAll([base,base],comparison),/DUPLICATE_RACE_KEYS/);
// Recovered research + archived legacy receipt for the SAME verified race must be linked,
// never counted as two different races. Missing PASS evidence or differing riders remains an error.
const linkedResearch=JSON.parse(JSON.stringify(base));
linkedResearch.raceKey='2026-10-05|75|1';
linkedResearch.audit={publicationPass:true};
const linkedLegacy=JSON.parse(JSON.stringify(comparison.races[0]));
linkedLegacy.finishers=linkedResearch.results.map(x=>({number:x.car,finish:x.finishRaw,name:x.name}));
linkedLegacy.formalPublication={status:'PASS',key:linkedResearch.raceKey};
const linked=auditAll([linkedResearch],{races:[linkedLegacy]});
assert.equal(linked.summary.allRaces,1);
assert.equal(linked.summary.evidenceRecords,2);
assert.equal(linked.summary.linkedExistingEvidencePairs,1);
assert.equal(linked.linkedEvidencePairs[0].key,linkedResearch.raceKey);
assert.equal(linked.summary.formalPass,0,'read-only audit never independently promotes');
const noProof=JSON.parse(JSON.stringify(linkedLegacy));delete noProof.formalPublication;
assert.throws(()=>auditAll([linkedResearch],{races:[noProof]}),/DUPLICATE_RACE_KEYS/);
const wrongRider=JSON.parse(JSON.stringify(linkedLegacy));
wrongRider.finishers[0].name='別人';
assert.throws(()=>auditAll([linkedResearch],{races:[wrongRider]}),/DUPLICATE_RACE_KEYS conflicting rider rows/);

const fs=require('node:fs'),path=require('node:path');
const dataDir=path.join(__dirname,'reconstruction-candidates');
// Historic full-field PASS pairs must be linked to their original receipts without being double-counted.
const historical=JSON.parse(fs.readFileSync(path.join(__dirname,'..','comparison-races-v1.json'),'utf8'));
const oldAndVerified=[1,2].map(n=>JSON.parse(fs.readFileSync(path.join(dataDir,'2026-10-05_75_'+n+'.research.json'),'utf8')));
for(const x of oldAndVerified)assert.equal(x.audit.publicationPass,true);
const historicAudit=auditAll(oldAndVerified,{races:historical.races});
assert.equal(historicAudit.summary.linkedExistingEvidencePairs,2);
assert.equal(historicAudit.summary.allRaces,historical.races.length);
assert.equal(historicAudit.summary.formalPass,0,'read-only audit never grants approval');
// Regression against real archived 2026-11-20 Nagoya 1-4R records after roster normalization.
// These assertions verify structure ONLY and must never assert official-source provenance.

for(const n of [1,2,3,4]){
 const d=JSON.parse(fs.readFileSync(path.join(dataDir,'2026-11-20_42_'+n+'.research.json'),'utf8'));
 const q=inspectSourceFirst(d);
 assert.equal(q.originalEntriesStructured,7,'original 7-card source must be structured for '+n);
 assert.equal(q.documentedRows,7);
 assert.equal(q.formationCars,7);
 assert.equal(q.numericFinishers,n===4?5:7);
 assert.equal(q.exceptionRows.length,n===4?2:0);
 assert.equal(q.publicationPassed,false);
 assert.ok(!q.blockers.includes('ORIGINAL_ENTRY_CARD_NOT_STRUCTURED'),'legacy entry schema issue must be resolved');
 assert.ok(!q.warnings.includes('LEGACY_FINISH_RAW_MISSING_NORMALIZE_WITHOUT_INVENTING'),'source rank raw schema must be normalized');
}
const legacy1=JSON.parse(fs.readFileSync(path.join(dataDir,'2026-11-20_42_1.research.json'),'utf8'));
assert.ok(inspectSourceFirst(legacy1).blockers.some(x=>x.startsWith('SOURCE_SB_MARKER_CONFLICT')),'do not erase historical S/B disagreement');
const legacy3=JSON.parse(fs.readFileSync(path.join(dataDir,'2026-11-20_42_3.research.json'),'utf8'));
assert.ok(inspectSourceFirst(legacy3).blockers.some(x=>x.startsWith('NUMERIC_FINISHER_LAP_NOT_DISPLAYED')),'do not invent seventh-place lap');
const priorAudit=JSON.parse(fs.readFileSync(path.join(__dirname,'audits','2026-11-23_acquired_18_races.json'),'utf8'));
assert.equal(priorAudit.summary.totalRaces,18);
assert.equal(priorAudit.summary.totalRiderRows,126);
assert.equal(priorAudit.summary.sourceFirstMissingOriginalEntries,0);
assert.equal(priorAudit.summary.formalPass,0);
console.log('OK: all-acquired-race audit catches legacy missing source mapping, blank laps, exception rows, duplicate races; NEVER publishes PASS');
