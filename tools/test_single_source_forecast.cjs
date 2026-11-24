#!/usr/bin/env node
'use strict';
// Offline synthetic checks: never publish the fabricated test race.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const base={
 'verified-results-feed-v1.json':JSON.parse(fs.readFileSync('verified-results-feed-v1.json')),
 'verified-rider-results-feed-v1.json':JSON.parse(fs.readFileSync('verified-rider-results-feed-v1.json')),
 'verified-rider-ids-feed-v1.json':JSON.parse(fs.readFileSync('verified-rider-ids-feed-v1.json')),
 'verified-line-snapshots-feed-v1.json':JSON.parse(fs.readFileSync('verified-line-snapshots-feed-v1.json'))
};
const synthetic={
 id:'2026-11-25|26|1',key:'2026-11-25|26|1',date:'2026-11-25',
 track:'西武園',trackCode:'26',race:1,size:7,verifiedDate:'2026-11-24',
 officialVerification:{status:'verified',source:'https://keirin.kdreams.jp/example/line-forecast',
  method:'published_single_source_forecast',forecastType:'media_prediction',
  matchingSources:['https://keirin.kdreams.jp/example/line-forecast'],
  sourceProof:{kind:'published_pre_race_forecast',provider:'kdreams',
   retrievedDate:'2026-11-24',evidenceRef:'SYNTHETIC-TEST-DO-NOT-PUBLISH'}},
 forecastGroups:[[3,1],[4,6],[5,2,7]],
 riders:Array.from({length:7},(_,i)=>({number:i+1,name:'試験選手'+(i+1),
  prefecture:'試験',period:'99',
  line:[[3,1],[4,6],[5,2,7]].find(g=>g.includes(i+1))}))
};
async function check(edit,success){
 const docs=structuredClone(base);
 docs['verified-line-snapshots-feed-v1.json'].races.push(structuredClone(synthetic));
 docs['verified-line-snapshots-feed-v1.json'].summary.races++;
 docs['verified-line-snapshots-feed-v1.json'].summary.rider_rows+=7;
 if(edit)edit(docs['verified-line-snapshots-feed-v1.json'].races.at(-1));
 const win={fetch:async path=>({ok:true,json:async()=>structuredClone(docs[path.replace(/^\.\//,'')])})};
 const code=fs.readFileSync('verified-publication-guard-v138.js','utf8');
 vm.runInNewContext(code,{window:win,URL,Date,Response,AbortController,setTimeout,clearTimeout},{timeout:3000});
 assert.equal(win.KIVerified.version,'13.8');
 if(success){let [results,rows,ids,lines]=await win.KIVerified.bundle();
  assert.ok(!results.races.some(x=>x.key===synthetic.key),'orphan result should remain unpublished');
  assert.ok(lines.races.some(x=>x.id===synthetic.key),'orphan media forecast accepted');}
 else{await assert.rejects(win.KIVerified.bundle());}
}
(async()=>{await check(null,true);
 await check(x=>{x.forecastGroups=[[3,1],[4,6],[5,2,2]]},false);
 await check(x=>{x.officialVerification.matchingSources=['https://other.example/line']},false);
 await check(x=>{x.riders[0].line=[1,3]},false);
 const individual=x=>{x.lineMode='no_line';x.raceFormat='girls';x.originalFormation='1234567';x.formatEvidenceUrl=x.officialVerification.source;x.forecastGroups=x.riders.map(r=>[r.number]);x.riders.forEach(r=>r.line=[r.number])};
 const contested=x=>{x.lineMode='contested';x.originalFormation='①（②③）④／⑤⑥／⑦';x.formatEvidenceUrl=x.officialVerification.source;x.forecastSlots=[[1,[2,3],4],[5,6],[7]];delete x.forecastGroups;x.riders.forEach(r=>delete r.line)};
 await check(contested,true);
 await check(x=>{contested(x);x.forecastSlots[0][1]=[2,2]},false);
 await check(x=>{contested(x);x.originalFormation='1234/56/7'},false);
 await check(x=>{contested(x);x.riders[1].line=[2,3]},false);
 await check(x=>{contested(x);x.formatEvidenceUrl='https://other.example/'},false);
 await check(individual,true);
 await check(x=>{individual(x);x.raceFormat='advance'},true);
 const unordered=x=>{individual(x);x.originalFormation='3517246';x.forecastGroups=[3,5,1,7,2,4,6].map(n=>[n])};
 await check(unordered,true);
 const invited=x=>{unordered(x);x.raceFormat='advance';const r=x.riders[0];r.prefecture='';r.period='';x.invitedRiders=[{number:r.number,name:r.name,entryName:r.name,kind:'foreign_invited',entryUrl:x.officialVerification.source,statusSourceUrl:x.formatEvidenceUrl,evidenceRef:'SYNTHETIC-GUEST-TEST'}]};
 await check(invited,true);
 await check(x=>{invited(x);delete x.invitedRiders},false);
 await check(x=>{invited(x);x.invitedRiders[0].entryName='different'},false);
 await check(x=>{invited(x);x.invitedRiders[0].statusSourceUrl=''},false);
 await check(x=>{unordered(x);x.raceFormat='advance'},true);
 await check(x=>{unordered(x);x.forecastGroups[6]=[2]},false);
 await check(x=>{individual(x);delete x.formatEvidenceUrl},false);
 await check(x=>{x.lineMode='no_line';x.raceFormat='girls';x.originalFormation='1234567';x.formatEvidenceUrl=x.officialVerification.source},false);
 console.log('OK: one-media pre-race forecast without a verified result; missing/duplicate cars, false sources and rearranged rider groups rejected');
})().catch(e=>{console.error(e);process.exitCode=1});
