#!/usr/bin/env node
'use strict';
// Offline integrity check. This does not claim external source agreement;
// the evidence records must be checked against their original sites separately.
const fs=require('node:fs');
const assert=require('node:assert/strict');
const load=name=>JSON.parse(fs.readFileSync(name,'utf8'));
const ids=load('verified-rider-ids-feed-v1.json');
const races=load('comparison-races-v1.json');
const official=load('verified-results-feed-v1.json');
const full=load('verified-rider-results-feed-v1.json');
const lines=load('verified-line-snapshots-feed-v1.json');
const domain=u=>{try{return new URL(u).hostname.replace(/^www\./,'')}catch{return ''}};
const requireUrl=u=>{assert.match(u,/^https:\/\//);assert.ok(domain(u),'invalid site URL')};
assert.equal(ids.summary.rows,ids.riders.length);
const idset=new Set(),personset=new Set();
for(const x of ids.riders){
 assert.match(x.id,/^\d{6}$/);assert.ok(x.name.trim()&&x.prefecture.trim());assert.match(x.period,/^\d+$/);
 assert.equal(x.officialVerification?.status,'verified');
 assert.equal(x.officialVerification?.method,'two_distinct_sites_agree');
 assert.deepEqual(new Set(x.officialVerification.fields),new Set(['name','prefecture','period','id']));
 const sources=x.officialVerification.matchingSources;
 assert.ok(Array.isArray(sources)&&sources.length>=2);
 for(const u of sources)requireUrl(u);
 assert.ok(new Set(sources.map(domain)).size>=2,'same source domain');
 assert.ok(sources.some(s=>domain(s)==='keirin.jp'&&s.includes(x.id)),'missing official matching id');
 assert.ok(!idset.has(x.id),'duplicate id');idset.add(x.id);
 const pk=[x.name.replace(/\s/g,''),x.prefecture.replace(/県|府|都$/g,''),x.period].join('|');
 assert.ok(!personset.has(pk),'duplicate identity');personset.add(pk);
}
assert.equal(races.summary.races,races.races.length);
assert.equal(races.summary.finishers,races.races.reduce((sum,r)=>sum+r.finishers.length,0));
const racekeys=new Set();
for(const r of races.races){
 assert.ok(!racekeys.has(r.key),'duplicate race');racekeys.add(r.key);
 assert.equal(r.key,[r.date,r.trackCode,r.race].join('|'));
 assert.ok([7,9].includes(r.finishers.length));
 assert.equal(r.resultAgreement,'all_required_comparison_fields_two_sites_agree');
 assert.equal(r.formation?.state,'two_site_agreement_recorded');
 assert.equal(r.formation?.type,'pre_race_published_prediction');
 assert.ok(Array.isArray(r.formation.sources)&&r.formation.sources.length>=2);
 r.formation.sources.forEach(requireUrl);
 assert.ok(new Set(r.formation.sources.map(domain)).size>=2,'not two source domains');
 const nums=r.finishers.map(x=>x.number),formed=r.formation.groups.flat();
 assert.equal(new Set(nums).size,nums.length);
 assert.equal(new Set(formed).size,formed.length);
 assert.deepEqual(nums.slice().sort((a,b)=>a-b),formed.slice().sort((a,b)=>a-b));
 assert.equal(new Set(r.finishers.map(x=>x.finish)).size,r.finishers.length);
 for(const x of r.finishers){assert.ok(x.name&&x.prefecture&&x.period&&x.riderClass,'missing rider identity');assert.ok(x.lastLap,'missing lap time');assert.ok('margin' in x&&'winningMethod' in x&&'startBack' in x&&'exception' in x,'missing comparison column')}
}
assert.equal(official.summary.races,official.races.length);
assert.equal(full.summary.rows,full.rows.length);
assert.equal(official.summary.rider_rows,full.rows.length);
assert.equal(lines.summary.races,lines.races.length);
console.log('OK: '+ids.riders.length+' rider IDs, '+races.races.length+' research races, '+races.summary.finishers+' finishers; verified official race stream '+official.races.length);
