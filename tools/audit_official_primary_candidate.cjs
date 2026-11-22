#!/usr/bin/env node
'use strict';
// Offline field comparison: researcher-supplied organizer/KEIRIN.JP original snapshot
// versus an existing research candidate. No network requests, publication or PASS writes.
const fs=require('node:fs');
const norm=s=>String(s??'').normalize('NFKC').replace(/[\s\u3000]/g,'');
const sortRows=xs=>xs.slice().sort((a,b)=>Number(a.car)-Number(b.car));
const method=x=>({逃げ:'逃',マーク:'ク',捲り:'捲',捲くり:'捲'}[norm(x)]||norm(x));
const marker=x=>norm(x).split('').sort().join('');
const rank=x=>String(x.finishRaw??x.finish??x.exceptionRaw??'').trim();
function audit(candidate,primary){
 const errors=[],unresolved=[],matched=[];
 const issue=(field,car,reason)=>unresolved.push({field,car,reason});
 if(primary?.schema!=='ki-official-primary-transcription-v1')errors.push('unknown official evidence schema');
 if(primary?.raceKey!==candidate?.raceKey)errors.push('race identity mismatch');
 if(primary?.issuer!=='JKA_KEIRIN_JP'&&primary?.issuer!=='ORGANIZER')errors.push('issuer not authenticated as official issuer');
 if(!/^https:\/\//.test(String(primary?.sourceUrl||'')))errors.push('official original source URL not recorded');
 const officialDomain=(()=>{try{return new URL(primary.sourceUrl).hostname}catch{return ''}})();
 if(primary?.issuer==='JKA_KEIRIN_JP'&&!/(^|\.)keirin\.jp$/.test(officialDomain))errors.push('KEIRIN.JP issuer URL host mismatch');
 if(!primary?.retrievedDateJST||!/^\d{4}-\d{2}-\d{2}/.test(primary.retrievedDateJST))errors.push('original retrieval date missing');
 if(!primary?.retrievalMethod||!primary?.originalRecordVerified)errors.push('original source identity/method has not been attested');
 if(primary?.generatedFromCandidate||primary?.exampleOnly)errors.push('synthetic/candidate-derived primary evidence forbidden');
 if(!Array.isArray(primary?.results)||!primary.results.length)errors.push('official full result rows not supplied');
 const result=Array.isArray(candidate?.results)?candidate.results:[];
 const original=Array.isArray(primary?.results)?primary.results:[];
 const byCar=new Map();
 for(const v of original){const car=Number(v.car);if(byCar.has(car))errors.push('duplicate primary car '+car);byCar.set(car,v);}
 if(original.length!==result.length)errors.push('primary/candidate row count mismatch');
 for(const row of result){
  const car=Number(row.car),orow=byCar.get(car);
  if(!orow){issue('row',car,'official rider/car absent');continue;}
  const checks=[
   ['name',norm(row.name),norm(orow.name)],['finish',rank(row),rank(orow)],
   ['lapSeconds',row.lapSeconds==null?null:Number(row.lapSeconds),orow.lapSeconds==null?null:Number(orow.lapSeconds)],
   ['marginRaw',norm(row.marginRaw),norm(orow.marginRaw)],
   ['winningMethodRaw',method(row.winningMethodRaw),method(orow.winningMethodRaw)],
   ['sbRaw',marker(row.sbRaw),marker(orow.sbRaw)],
   ['exceptionRaw',norm(row.exceptionRaw),norm(orow.exceptionRaw)]
  ];
  for(const [field,a,b] of checks){
   if(b===null||b===''&&(field==='lapSeconds'||field==='sbRaw'&&a)){
     if(a!==b)issue(field,car,'official source field not displayed / missing; never infer zero');
     else if(field==='lapSeconds')issue(field,car,'both blank: applicability not established');
   }else if(a!==b)issue(field,car,'candidate differs from official original');
   else matched.push({car,field});
  }
 }
 const ready=errors.length===0&&unresolved.length===0;
 return {raceKey:candidate?.raceKey,sourceUrl:primary?.sourceUrl||null,issuer:primary?.issuer||null,status:ready?'FIELD_MATCH_ONLY_STILL_REQUIRES_SECONDARY_CORROBORATION_AND_PUBLICATION_GATE':'NOT_READY',matchedFields:matched.length,unresolved,errors,publicationPassed:false};
}
function main(){
 if(process.argv.length!==4)throw Error('Usage: node tools/audit_official_primary_candidate.cjs research.json official-manually-verified.json');
 const c=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),p=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
 console.log(JSON.stringify(audit(c,p),null,2));
}
if(require.main===module){try{main()}catch(e){console.error(e.message);process.exitCode=1}}
module.exports={audit};
