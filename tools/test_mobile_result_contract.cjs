#!/usr/bin/env node
'use strict';
// UI-only static regression check. Published data integrity is checked by check_publication_completeness.cjs.
// Passing does not verify rendered iPhone Safari UI.
const fs=require('node:fs');
const assert=require('node:assert/strict');
const html=fs.readFileSync('race-result-detail.html','utf8');
const researchHtml=fs.readFileSync('reconstruction-status.html','utf8');
const requiredLabels=['選手コメントに基づく事前ライン構成','事前の並び予想','確定上位3車','着順','車番','選手名','上がり','着差','決まり手','S/B','府県','期別','展開未検証'];
for(const label of requiredLabels)assert.ok(html.includes(label),'mobile UI missing label: '+label);
for(const label of ['確定上位3車','着順','車番','選手名','上がり','着差・決まり手・S/B・府県・期別・例外','コメントで部分確認','正式PASS・公開フィードに接続'])assert.ok(researchHtml.includes(label),'research mobile UI missing label: '+label);
assert.ok(researchHtml.includes("d.audit?.publicationPass===true"),'research status must not claim PASS without matching evidence');
assert.ok(researchHtml.includes("d.preRaceFormation?.partialSupportedPair&&!groups.length"),'partial pre-race comments cannot auto-create a whole formation');
assert.ok(html.includes('Array.isArray(x.forecastGroups)'),'must preserve verified forecast group order; result-row order is not lineup order');
assert.ok(html.includes('top.map(x=>x.number).join("－")'),'top 3 must be printed in finish order');
assert.ok(html.includes('lineup(line,r.size)'),'must validate complete lineup before display');
assert.ok(html.includes('pref(y.prefecture)!==pref(x.prefecture)'),'must validate matching rider identity');
const colors=['#f4f4f4','#242424','#d84242','#2d5fbb','#efd849','#278850','#ed9337','#dfa1c9','#8254ae'];
for(const color of colors)assert.ok(html.includes(color),'missing keirin car color '+color);
const forecast=fs.readFileSync('line-forecast.html','utf8');
const home=fs.readFileSync('index.html','utf8');
assert.ok(home.includes('href="./line-forecast.html"'),'home must link independent line forecast view');
assert.ok(home.includes('window.KIVerified.validate(a,b,i,l);'),'home must use shared publication guard');
assert.ok(!home.includes('function verifyPublication(a,b,i,l){'),'home must not retain old two-source forecast validator');
for(const label of ['媒体の並び予想','脚見せ','他媒体との一致も要求しません','forecastGroups'])assert.ok(forecast.includes(label),'forecast page missing '+label);
assert.ok(forecast.includes('results.has(r.id)'),'orphan forecast must be visible without result');
console.log('OK: mobile UI labels, numbered car colors, pre-race forecast rendering guards (static HTML checks only; published feed validation is handled by check_publication_completeness.cjs).');
