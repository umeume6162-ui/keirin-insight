#!/usr/bin/env node
"use strict";
// Offline regression: use exactly the helper functions shipped in daily-board.html.
// No browser, remote feed, or Google credentials required.
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const html=fs.readFileSync("daily-board.html","utf8");
const start=html.indexOf("function badge(number){");
const end=html.indexOf("function buildRace(r){",start);
assert(start>=0&&end>start,"Expected daily-board visual helper functions");
const context={};
vm.runInNewContext(html.slice(start,end)+
  "\nthis.checkLines=allLines;this.checkTopThree=topThree;",context);
const make=(groups)=>groups.flatMap(g=>g.map(n=>({number:n,preRaceLine:g.length===1?"単騎":g.join("-")})));
const groups=make([[4,1],[2,7,5],[6,3]]);
assert.deepEqual(Array.from(context.checkLines(groups),g=>Array.from(g)).map(g=>g.join("-")),
  ["4-1","2-7-5","6-3"]);
assert.equal(context.checkLines(groups.slice(0,6)),null,"Incomplete field must not imply singleton");
const conflicting=make([[4,1],[2,7,5],[6,3]]);
conflicting[0].preRaceLine="4-2";
assert.equal(context.checkLines(conflicting),null,"Conflicting lineup must be withheld");
const unknown=make([[4,1],[2,7,5],[6,3]]);
unknown[3].preRaceLine="";
assert.equal(context.checkLines(unknown),null,"Unknown line must be withheld");
assert.equal(context.checkLines(make([[1,2,3],[4,5,6],[7,8,9]])).length,3);
const finishes=[{number:2,finish:"1"},{number:7,finish:"2"},
  {number:3,finish:"3"},{number:1,finish:"4"},
  {number:4,finish:"5"},{number:5,finish:"6"},{number:6,finish:"7"}];
assert.deepEqual(Array.from(context.checkTopThree(finishes)),[2,7,3]);
assert.equal(context.checkTopThree(finishes.slice(0,6)),null);
const deadheat=finishes.map(x=>({...x}));
deadheat[3].finish="1";
assert.equal(context.checkTopThree(deadheat),null,"Non-unique first must not render ranking");
assert.ok(html.includes('body.append(riderEntryList(entries,r));'),'racecard must show rider table immediately');
assert.ok(!html.includes('extra.append(riderEntryList(entries,r));'),'rider table must not be nested in closed details');
for(const label of ['出走表｜選手・競走データ','2連対率','3連対率','勝率','S','B'])assert.ok(html.includes(label),'rider metrics must be labeled: '+label);
assert.ok(html.includes('entry-stats-wrap')&&html.includes('position:sticky'),'mobile table must be horizontally scrollable with frozen identities');
assert.ok(html.includes('hasStats&&e.riderStats'),'do not fabricate missing statistics');
console.log("DAILY_BOARD_UI_TEST_OK: 7/9-car groups, singleton, unknown, conflict, ranked result");
