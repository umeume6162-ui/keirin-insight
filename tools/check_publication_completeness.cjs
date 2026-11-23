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
const kdSource=u=>/^https:\/\/keirin\.kdreams\.jp\//.test(String(u||''));
const kdEvidence=r=>{const e=r.officialVerification,p=e?.sourceProof;return e?.status==='verified'&&e?.method==='kdreams_single_source_verified'&&kdSource(e.source)&&Array.isArray(e.matchingSources)&&e.matchingSources.length===1&&e.matchingSources[0]===e.source&&p&&['live_html','preserved_original_html'].includes(p.kind)&&/^\d{4}-\d\d-\d\d$/.test(p.retrievedDate)&&typeof p.evidenceRef==='string'&&p.evidenceRef.trim().length>8};
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
 assert.ok(sources.some(s=>s.includes(x.id)),'missing identity-linked evidence URL');
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
 // Numeric places and non-finishing statuses are different data types. Never fill in
 // a missing placing simply to make the expected rider count match.
 const ranks=r.finishers.filter(x=>/^\d+$/.test(String(x.finish||''))).map(x=>Number(x.finish));
 assert.equal(new Set(ranks).size,ranks.length,'duplicate numeric finish');
 assert.ok(ranks.every(n=>n>=1&&n<=r.finishers.length),'finish outside field');
 const statusValues=new Set(['欠車','取消','失格','落車棄権','途中棄権','棄権']);
 for(const x of r.finishers){
   assert.ok(x.name&&x.prefecture&&x.period&&x.riderClass,'missing rider identity');
   assert.ok('margin' in x&&'winningMethod' in x&&'startBack' in x&&'exception' in x,'missing comparison column');
   if(/^\d+$/.test(String(x.finish||''))){assert.ok(x.lastLap,'missing numeric finisher lap')}
   else{
     assert.ok(statusValues.has(String(x.finish)),'unverified or ambiguous finish status');
     assert.equal(x.exception,x.finish,'exception status mismatch');
     assert.ok(Array.isArray(x.exceptionSourceUrls)&&new Set(x.exceptionSourceUrls.map(domain)).size>=2,'exception requires two distinct source domains');
   }
 }
}
assert.equal(official.summary.races,official.races.length);
assert.equal(full.summary.rows,full.rows.length);
assert.equal(official.summary.rider_rows,full.rows.length);
assert.equal(lines.summary.races,lines.races.length);
assert.equal(lines.summary.rider_rows,lines.races.reduce((n,r)=>n+r.riders.length,0));
assert.equal(full.summary.races,official.summary.races);
assert.equal(official.summary.rider_rows,full.rows.length);
const groupsAreValid=groups=>Array.isArray(groups)&&groups.every(g=>Array.isArray(g)&&g.length&&g.every(n=>Number.isInteger(Number(n))));
const fieldIndex=Object.fromEntries(full.columns.map((k,i)=>[k,i]));
const raceByKey=new Map(official.races.map(r=>[r.key,r]));
const verifiedRaceKeys=new Set();
for(const race of official.races){
 const key=[race.date,String(race.track_code),Number(race.race)].join('|');
 assert.equal(race.key,key,'published race key mismatch');
 assert.ok(!verifiedRaceKeys.has(key),'duplicate published race');verifiedRaceKeys.add(key);
 assert.ok([7,9].includes(race.size),'verified result size must be 7 or 9');
 // Publication-facing provenance is checked here, not repeated by the mobile UI test.
 const isKD=kdEvidence(race);
 if(!isKD)assert.ok(['rider_comments_and_published_forecast','published_forecast'].includes(race.preRaceFormation?.basis),'missing forecast heading provenance');
 assert.equal(race.officialVerification?.status,'verified');
 assert.ok(isKD||race.officialVerification?.method==='two_distinct_sites_agree','unknown verification method');
 const rs=race.officialVerification.matchingSources||[];
 if(isKD)assert.deepEqual(rs,[race.officialVerification.source],'K-Dreams proof must have one source');
 else assert.ok(new Set(rs.map(domain)).size>=2,'legacy result needs two sources');
 rs.forEach(requireUrl);
 const riderRows=full.rows.filter(row=>[row[fieldIndex.date],String(row[fieldIndex.trackCode]),Number(row[fieldIndex.race])].join('|')===key);
 assert.equal(riderRows.length,race.size,'published result must contain entire field');
 const cars=riderRows.map(row=>Number(row[fieldIndex.number]));
 assert.equal(new Set(cars).size,race.size,'duplicate result car');
 for(const row of riderRows){
  assert.equal(row.length,full.columns.length,'result row width');
  assert.ok(rs.includes(row[fieldIndex.sourceUrl]),'rider result URL not in verified result sources');
  if(isKD)assert.ok(kdSource(row[fieldIndex.sourceUrl]),'K-Dreams result has foreign source');
  for(const mandatory of (isKD?['name','prefecture','period','finishRaw','riderClass']:['name','prefecture','period','finishRaw','riderClass','lastLapRaw'])){
   assert.ok(String(row[fieldIndex[mandatory]]??'').trim(),'missing verified rider field: '+mandatory);
  }
 }
 const line=lines.races.find(x=>x.id===key);
 if(isKD&&!line)continue;
 assert.ok(line,'legacy verified race requires matched pre-race lineup');
 assert.equal(line.officialVerification?.status,'verified');
 assert.ok(line.officialVerification?.method==='two_distinct_sites_agree'||(isKD&&line.officialVerification?.method==='kdreams_single_source_verified'),'invalid forecast provenance');
 const ls=line.officialVerification.matchingSources||[];
 if(line.officialVerification.method==='kdreams_single_source_verified')assert.ok(ls.length===1&&kdSource(ls[0]),'K-Dreams single forecast proof');
 else assert.ok(new Set(ls.map(domain)).size>=2,'legacy lineup needs two sources');ls.forEach(requireUrl);
 assert.equal(line.riders.length,race.size,'lineup rider count');
 const lineCars=line.riders.map(x=>Number(x.number));
 assert.deepEqual(lineCars.slice().sort((a,b)=>a-b),cars.slice().sort((a,b)=>a-b),'lineup/result car mismatch');
 assert.ok(groupsAreValid(line.forecastGroups),'lineup groups invalid');
 const grouped=line.forecastGroups.flat().map(Number);
 assert.equal(new Set(grouped).size,race.size,'lineup duplicate/missing car');
 assert.deepEqual(grouped.slice().sort((a,b)=>a-b),cars.slice().sort((a,b)=>a-b));
 for(const rider of line.riders){
  const row=riderRows.find(x=>Number(x[fieldIndex.number])===Number(rider.number));
  assert.ok(row,'missing linked rider row');
  assert.equal(String(row[fieldIndex.name]).replace(/\s/g,''),String(rider.name).replace(/\s/g,''));
  assert.equal(String(row[fieldIndex.period]),String(rider.period));
  assert.ok(Array.isArray(rider.line)&&rider.line.some(n=>Number(n)===Number(rider.number)));
  assert.ok(line.forecastGroups.some(g=>JSON.stringify(g)===JSON.stringify(rider.line)),'line group not corroborated');
 }
}
assert.ok(lines.races.every(x=>verifiedRaceKeys.has(x.id)),'orphan lineup publication');
console.log('OK: '+ids.riders.length+' rider IDs, '+races.races.length+' research races, '+races.summary.finishers+' finishers; verified official race stream '+official.races.length);
