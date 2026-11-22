#!/usr/bin/env node
'use strict';
// Static contract regression check. Passing does not verify rendered iPhone Safari UI.
const fs=require('node:fs');
const assert=require('node:assert/strict');
const html=fs.readFileSync('race-result-detail.html','utf8');
const feed=JSON.parse(fs.readFileSync('verified-results-feed-v1.json','utf8'));
const lines=JSON.parse(fs.readFileSync('verified-line-snapshots-feed-v1.json','utf8'));
const requiredLabels=['選手コメントに基づく事前ライン構成','事前の並び予想','確定上位3車','着順','車番','選手名','上がり','着差','決まり手','S/B','府県','期別','展開未検証'];
for(const label of requiredLabels)assert.ok(html.includes(label),'mobile UI missing label: '+label);
assert.ok(html.includes('Array.isArray(x.forecastGroups)'),'must preserve verified forecast group order; result-row order is not lineup order');
assert.ok(html.includes('top.map(x=>x.number).join("－")'),'top 3 must be printed in finish order');
assert.ok(html.includes('lineup(line,r.size)'),'must validate complete lineup before display');
assert.ok(html.includes('pref(y.prefecture)!==pref(x.prefecture)'),'must validate matching rider identity');
const colors=['#f4f4f4','#242424','#d84242','#2d5fbb','#efd849','#278850','#ed9337','#dfa1c9','#8254ae'];
for(const color of colors)assert.ok(html.includes(color),'missing keirin car color '+color);
for(const race of feed.races){
 const line=lines.races.find(x=>x.id===race.key);
 assert.ok(line,'published race missing line '+race.key);
 assert.equal(race.size,line.riders.length);
 assert.deepEqual(line.forecastGroups,race.preRaceFormation.groups,'published lineup differs');
 assert.ok(['rider_comments_and_published_forecast','published_forecast'].includes(race.preRaceFormation.basis),'missing forecast heading provenance');
 assert.equal(new Set(line.forecastGroups.flat()).size,race.size,'incomplete lineup');
}
console.log('OK: mobile race-result labels, numbered chips, source-based heading, preserved 7/9-car forecast ordering and '+feed.races.length+' feed records (static code and JSON only).');
