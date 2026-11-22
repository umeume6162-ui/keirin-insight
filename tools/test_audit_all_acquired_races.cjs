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
console.log('OK: all-acquired-race audit catches legacy missing source mapping, blank laps, exception rows, duplicate races; NEVER publishes PASS');
