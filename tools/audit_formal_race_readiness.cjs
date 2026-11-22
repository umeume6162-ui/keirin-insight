#!/usr/bin/env node
'use strict';
// Read-only readiness audit. Never turns an old PENDING flag into a new approval gate.
// Report missing *verifiable evidence fields* before mapping to the official feeds.
const fs=require('node:fs');
const research=JSON.parse(fs.readFileSync('comparison-races-v1.json','utf8'));
const official=JSON.parse(fs.readFileSync('verified-results-feed-v1.json','utf8'));
const rows=JSON.parse(fs.readFileSync('verified-rider-results-feed-v1.json','utf8'));
const lines=JSON.parse(fs.readFileSync('verified-line-snapshots-feed-v1.json','utf8'));
const host=u=>{try{return new URL(u).hostname.replace(/^www\\./,'')}catch{return ''}};
const requiredResultFields=['finish','number','name','prefecture','period','riderClass','margin','lastLap','winningMethod','startBack','exception'];
const audits=research.races.map(r=>{
 const missing=[];
 const finishers=Array.isArray(r.finishers)?r.finishers:[];
 const nums=finishers.map(x=>x.number),expected=[7,9].includes(nums.length)?nums.length:null;
 if(!expected||new Set(nums).size!==expected)missing.push('seven/nine distinct finisher-or-status identities');
 if(!r.formation||r.formation.state!=='two_site_agreement_recorded')missing.push('complete pre-race formation two-site confirmation');
 const lineSources=r.formation?.sources||[];
 if(new Set(lineSources.map(host)).size<2)missing.push('two independent pre-race formation domains');
 if(r.formation?.groups?.flat().slice().sort((a,b)=>a-b).join(',')!==nums.slice().sort((a,b)=>a-b).join(','))missing.push('lineup/result car coverage');
 for(const [n,x] of finishers.entries())for(const k of requiredResultFields)if(!(k in x))missing.push('row '+(n+1)+' missing '+k);
 // A generic comparison sentence is not per-field two-provider evidence.
 if(!r.resultEvidenceByField||!Array.isArray(r.resultEvidenceByField)||r.resultEvidenceByField.length!==expected)
  missing.push('per-rider/per-required-result-field two-provider source evidence');
 if(!r.officialVerification?.source||!/^https:\/\/(?:www\\.)?keirin\\.jp\//.test(r.officialVerification.source))
  missing.push('official-source receipt/reference for formal race index');
 if(!r.officialVerification?.verifiedDate)missing.push('race verification timestamp');
 return {key:r.key,entered:finishers.length,forecast:r.formation?.groups?.map(g=>g.join('-')).join(' / '),status:missing.length?'NEEDS_SOURCE_EVIDENCE':'READY_FOR_SCHEMA_MAPPING',missing};
});
const report={generatedBy:'tools/audit_formal_race_readiness.cjs',publicationDecision:'no promotion performed',researchRaces:research.races.length,officialRaces:official.races.length,officialRiderRows:rows.rows.length,officialLineSnapshots:lines.races.length,audits};
console.log(JSON.stringify(report,null,2));
if(audits.some(x=>x.status==='READY_FOR_SCHEMA_MAPPING'))process.exitCode=0;
