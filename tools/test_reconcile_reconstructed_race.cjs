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
// Maebashi 2R: source-origin and third-source S-field omissions never promote research data.
const maebashi2=check(JSON.parse(fs.readFileSync(path.join(base,'2026-11-20_22_2.research.json'),'utf8')));
assert.equal(maebashi2.raceKey,'2026-11-20|22|2');
assert.equal(maebashi2.structuralOk,true,JSON.stringify(maebashi2.errors));
assert.equal(maebashi2.documentedResultRows,7);
assert.equal(maebashi2.numericFinishers,7);
assert.deepEqual(maebashi2.missingFromResult,[]);
assert.equal(maebashi2.publicationPassed,false);
assert.equal(maebashi2.officialStartersKnown,false);
const maebashi=check(JSON.parse(fs.readFileSync(path.join(base,'2026-11-20_22_1.research.json'),'utf8')));
assert.equal(maebashi.raceKey,'2026-11-20|22|1');
assert.equal(maebashi.structuralOk,true,JSON.stringify(maebashi.errors));
assert.equal(maebashi.documentedResultRows,7);
assert.equal(maebashi.numericFinishers,7);
assert.deepEqual(maebashi.missingFromResult,[]);
assert.equal(maebashi.officialStartersKnown,false);
assert.equal(maebashi.publicationPassed,false);
// Maebashi 3R: independent venue regression and explicit nonpublication of source-first data.
const maebashi3=check(JSON.parse(fs.readFileSync(path.join(base,'2026-11-20_22_3.research.json'),'utf8')));
assert.equal(maebashi3.raceKey,'2026-11-20|22|3');
assert.equal(maebashi3.structuralOk,true,JSON.stringify(maebashi3.errors));
assert.equal(maebashi3.documentedResultRows,7);
assert.equal(maebashi3.numericFinishers,7);
assert.deepEqual(maebashi3.missingFromResult,[]);
assert.equal(maebashi3.officialStartersKnown,false);
assert.equal(maebashi3.publicationPassed,false);
// Recovered 2026-10-05 Matsuyama 7R: historical source rows, seven cars, but predicted formation and primary evidence still unverified.
const matsuyama7=check(JSON.parse(fs.readFileSync(path.join(base,'2026-10-05_75_7.research.json'),'utf8')));
assert.equal(matsuyama7.raceKey,'2026-10-05|75|7');
assert.equal(matsuyama7.structuralOk,true,JSON.stringify(matsuyama7.errors));
assert.equal(matsuyama7.documentedResultRows,7);
assert.equal(matsuyama7.numericFinishers,7);
assert.deepEqual(matsuyama7.missingFromResult,[]);
assert.equal(matsuyama7.publicationPassed,false);
assert.equal(matsuyama7.officialStartersKnown,false);
assert.ok(matsuyama7.warnings.some(w=>w.includes('pre-race formation does not cover entire original card')));
// Recovered Matsuyama 8R: 7 historical ranked results are consistent; original amended entries and line groups remain unverified.
const matsuyama8=check(JSON.parse(fs.readFileSync(path.join(base,'2026-10-05_75_8.research.json'),'utf8')));
assert.equal(matsuyama8.raceKey,'2026-10-05|75|8');
assert.equal(matsuyama8.structuralOk,true,JSON.stringify(matsuyama8.errors));
assert.equal(matsuyama8.documentedResultRows,7);
assert.equal(matsuyama8.numericFinishers,7);
assert.deepEqual(matsuyama8.missingFromResult,[]);
assert.equal(matsuyama8.publicationPassed,false);
assert.equal(matsuyama8.officialStartersKnown,false);
assert.ok(matsuyama8.warnings.some(w=>w.includes('pre-race formation does not cover entire original card')));
// Matsuyama 9R retained seven archived result identities with 49 saved-field matches;
// search-index results are not independent primary originals and cannot promote publication.
const matsuyama9=check(JSON.parse(fs.readFileSync(path.join(base,'2026-10-05_75_9.research.json'),'utf8')));
assert.equal(matsuyama9.raceKey,'2026-10-05|75|9');
assert.equal(matsuyama9.structuralOk,true,JSON.stringify(matsuyama9.errors));
assert.equal(matsuyama9.documentedResultRows,7);
assert.equal(matsuyama9.numericFinishers,7);
assert.deepEqual(matsuyama9.missingFromResult,[]);
assert.equal(matsuyama9.publicationPassed,false);
assert.equal(matsuyama9.officialStartersKnown,false);
assert.ok(matsuyama9.warnings.some(w=>w.includes('pre-race formation does not cover entire original card')));
// Matsuyama 10R: archived results agree, but an independent original start roster was NOT retrieved.
const matsuyama10=check(JSON.parse(fs.readFileSync(path.join(base,'2026-10-05_75_10.research.json'),'utf8')));
assert.equal(matsuyama10.raceKey,'2026-10-05|75|10');
assert.equal(matsuyama10.structuralOk,true,JSON.stringify(matsuyama10.errors));
assert.equal(matsuyama10.documentedResultRows,7);
assert.equal(matsuyama10.numericFinishers,7);
assert.deepEqual(matsuyama10.missingFromResult,[]);
assert.equal(matsuyama10.publicationPassed,false);
assert.equal(matsuyama10.officialStartersKnown,false);
assert.ok(matsuyama10.warnings.some(w=>w.startsWith('RESULT_DERIVED_ENTRIES_ONLY')));
assert.ok(matsuyama10.warnings.some(w=>w.includes('pre-race formation does not cover entire original card')));
// Matsuyama 11R: 49 archived result fields match two providers. Line groups remain independently pending.
const matsuyama11=JSON.parse(fs.readFileSync(path.join(base,'2026-10-05_75_11.research.json'),'utf8'));
const mat11check=check(matsuyama11);
assert.equal(mat11check.structuralOk,true,JSON.stringify(mat11check.errors));
assert.equal(mat11check.documentedResultRows,7);
assert.equal(mat11check.numericFinishers,7);
assert.deepEqual(mat11check.missingFromResult,[]);
assert.equal(matsuyama11.fieldVerification.resultFields.status,'TWO_SITES_ARCHIVED_MATCH');
assert.equal(matsuyama11.fieldVerification.forecastLine.status,'PENDING');
assert.equal(mat11check.publicationPassed,false);
assert.ok(mat11check.warnings.some(w=>w.includes('pre-race formation does not cover entire original card')));
// Matsuyama 12R: 2 provider result receipts and complete three-line forecast are formally recorded.
const matsuyama12=JSON.parse(fs.readFileSync(path.join(base,'2026-10-05_75_12.research.json'),'utf8'));
const mat12check=check(matsuyama12);
assert.equal(mat12check.structuralOk,true,JSON.stringify(mat12check.errors));
assert.equal(mat12check.documentedResultRows,7);
assert.equal(mat12check.numericFinishers,7);
assert.deepEqual(mat12check.missingFromResult,[]);
assert.equal(mat12check.officialStartersKnown,false);
assert.equal(mat12check.publicationPassed,false,'structural check never self-promotes');
assert.equal(matsuyama12.audit.publicationPass,true,'formal source record tracks independent business decision');
assert.equal(matsuyama12.fieldVerification.resultFields.fieldComparisons,49);
assert.deepEqual(matsuyama12.preRaceFormation.groups,[[1,4,6],[5,2],[3,7]]);
assert.equal(new Set(matsuyama12.preRaceFormation.groups.flat()).size,7);
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
console.log('source-first race reconciliation tests passed (10 authentic candidates + missing/duplicate regression cases)');
