#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {check}=require('./reconcile_reconstructed_race.cjs');
const base=path.join(__dirname,'reconstruction-candidates');
const load=n=>JSON.parse(fs.readFileSync(path.join(base,'2026-11-20_42_'+n+'.research.json'),'utf8'));
// All three stored racecards and source-first results must parse without losing car/exception rows.
const r5=check(load(5));
assert.equal(r5.raceKey,'2026-11-20|42|5');
assert.equal(r5.structuralOk,true,JSON.stringify(r5.errors));
assert.equal(r5.documentedResultRows,7);
assert.equal(r5.numericFinishers,7);
assert.deepEqual(r5.missingFromResult,[]);
assert.equal(r5.publicationPassed,false);
assert.equal(r5.officialStartersKnown,false);
// A newly reconstructed race with all seven original cards and numeric results must match each car exactly.
const r6=check(load(6));
assert.equal(r6.raceKey,'2026-11-20|42|6');
assert.equal(r6.structuralOk,true,JSON.stringify(r6.errors));
assert.equal(r6.documentedResultRows,7);
assert.equal(r6.numericFinishers,7);
assert.deepEqual(r6.missingFromResult,[]);
assert.equal(r6.publicationPassed,false);
assert.equal(r6.officialStartersKnown,false);
// Five numeric places plus fall/disqualification must be retained without ranking the exceptions.
const r4=check(load(4));
assert.equal(r4.structuralOk,true,JSON.stringify(r4.errors));
assert.equal(r4.numericFinishers,5);
assert.equal(r4.nonNumericResultRows.length,2);
assert.equal(r4.publicationPassed,false);
// Numeric seventh place with blank lap is still a numeric finish.
const r3=check(load(3));
assert.equal(r3.structuralOk,true,JSON.stringify(r3.errors));
assert.equal(r3.numericFinishers,7);
assert.equal(r3.publicationPassed,false);
const corrupted=load(5);
corrupted.results.pop();
const missing=check(corrupted);
assert.equal(missing.structuralOk,true);
assert.ok(missing.warnings.some(w=>w.includes('ENTRY_ONLY_CAR')));
assert.equal(missing.publicationPassed,false);
const duplicate=load(5);
duplicate.results[1].car=duplicate.results[0].car;
assert.equal(check(duplicate).structuralOk,false);
console.log('source-first race reconciliation tests passed (4 authentic candidates + missing/duplicate regression cases)');
