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
// Newly saved 7R: seven original entrants, seven numeric results, and full pre-race line coverage.
const r7=check(load(7));
assert.equal(r7.raceKey,'2026-11-20|42|7');
assert.equal(r7.structuralOk,true,JSON.stringify(r7.errors));
assert.equal(r7.documentedResultRows,7);
assert.equal(r7.numericFinishers,7);
assert.equal(r7.missingFromResult.length,0);
assert.equal(r7.publicationPassed,false);
assert.equal(r7.officialStartersKnown,false);
// Nagoya 8R preserves all seven entrants, finish ranks and pre-race groups without auto-promotion.
const r8=check(load(8));
assert.equal(r8.raceKey,'2026-11-20|42|8');
assert.equal(r8.structuralOk,true,JSON.stringify(r8.errors));
assert.equal(r8.documentedResultRows,7);
assert.equal(r8.numericFinishers,7);
assert.deepEqual(r8.missingFromResult,[]);
assert.equal(r8.publicationPassed,false);
assert.equal(r8.officialStartersKnown,false);
// Nagoya 9R: 7 original entries, 5 placed results, and exactly two original exception statuses.
const r9=check(load(9));
assert.equal(r9.raceKey,'2026-11-20|42|9');
assert.equal(r9.structuralOk,true,JSON.stringify(r9.errors));
assert.equal(r9.documentedResultRows,7);
assert.equal(r9.numericFinishers,5);
assert.deepEqual(r9.nonNumericResultRows.map(x=>[x.car,x.status]),[[3,'落'],[6,'失']]);
assert.deepEqual(r9.missingFromResult,[]);
assert.equal(r9.publicationPassed,false);
assert.equal(r9.officialStartersKnown,false);
// First race outside Nagoya: seven Maebashi A3 starters on the dated card and seven ranked results.
const maebashi=check(JSON.parse(fs.readFileSync(path.join(base,'2026-11-20_22_1.research.json'),'utf8')));
assert.equal(maebashi.raceKey,'2026-11-20|22|1');
assert.equal(maebashi.structuralOk,true,JSON.stringify(maebashi.errors));
assert.equal(maebashi.documentedResultRows,7);
assert.equal(maebashi.numericFinishers,7);
assert.deepEqual(maebashi.missingFromResult,[]);
assert.equal(maebashi.officialStartersKnown,false);
assert.equal(maebashi.publicationPassed,false);
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
console.log('source-first race reconciliation tests passed (8 authentic candidates + missing/duplicate regression cases)');
