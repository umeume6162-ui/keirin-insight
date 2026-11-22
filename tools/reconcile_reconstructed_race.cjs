#!/usr/bin/env node
'use strict';
// Read-only, source-respecting structural reconciliation for KI research candidates.
// This does NOT determine whether sources are genuinely independent and never promotes to PASS.
const fs = require('node:fs');
const numeric = x => Number.isInteger(x) && x > 0 && x <= 9;
function check(r) {
 const errors=[], warnings=[];
 const add=(a,s)=>a.push(s);
 const key=r.raceKey||'', count=r.race?.expectedEntrants;
 const entries=Array.isArray(r.originalEntries)?r.originalEntries:null;
 const result=Array.isArray(r.results)?r.results:[];
 if(!/^\\d{4}-\\d{2}-\\d{2}\\|\\d{2}\\|(?:[1-9]|1[0-2])$/.test(key))add(errors,'invalid race key');
 if(![7,9].includes(count))add(errors,'race size not 7 or 9');
 if(!result.length)add(errors,'missing result rows');
 const cs=new Set(), numericFinishes=new Set();
 for(const x of result) {
   const car=Number(x.car);
   if(!numeric(car))add(errors,'invalid result car '+x.car);
   if(cs.has(car))add(errors,'duplicate result car '+car);
   cs.add(car);
   const raw=String(x.finishRaw??x.finish??'').trim();
   if(/^\\d+$/.test(raw)){
     const n=Number(raw); if(n<1||n>9||numericFinishes.has(n))add(errors,'invalid/duplicate numeric finish '+raw);
     numericFinishes.add(n);
     if(x.finish!==undefined&&x.finish!==null&&Number(x.finish)!==n)add(errors,'finish/raw mismatch '+car);
   }else if(!raw && !String(x.exceptionRaw??'').trim()){
     add(errors,'unlabeled result row '+car);
   }else{
     if(x.finish!==null&&x.finish!==undefined)add(errors,'exception row has numeric finish '+car);
     if(x.exceptionRaw && raw && raw!==String(x.exceptionRaw).trim())add(warnings,'exception label mismatch car '+car);
   }
 }
 let entryCars=[];
 if(entries){
   entryCars=entries.map(x=>Number(x.car));
   if(new Set(entryCars).size!==entryCars.length)add(errors,'duplicate entry cars');
   if(entryCars.some(x=>!numeric(x)))add(errors,'invalid entry car');
   if(entryCars.length!==count)add(warnings,'entry card count differs from expected; amended racecard required');
   for(const c of cs)if(!entryCars.includes(c))add(errors,'result car not found in entry card '+c);
   for(const c of entryCars)if(!cs.has(c))add(warnings,'ENTRY_ONLY_CAR '+c+': check revised racecard, official withdrawal/欠車, and exception results');
 }else add(warnings,'MISSING_ORIGINAL_ENTRY_CARD: do not assume entrants=starters');
 const line=r.preRaceFormation?.groups;
 if(Array.isArray(line)){
   const cars=line.flat().map(Number);
   if(new Set(cars).size!==cars.length)add(errors,'duplicated pre-race line car');
   if(entryCars.length&&cars.some(c=>!entryCars.includes(c)))add(errors,'line includes non-entry car');
   if(entryCars.length&&entryCars.some(c=>!cars.includes(c)))add(warnings,'pre-race formation does not cover entire original card');
 }else add(warnings,'missing pre-race formation');
 if(!r.reconciliation?.revisedStartCardSource)add(warnings,'REVISED_RACECARD_NOT_VERIFIED: actual start count is not certified by original card alone');
 if(!r.fieldVerification || /PASS/i.test(String(r.status||''))&&!/NOT_VERIFIED_PASS/.test(String(r.status)))add(warnings,'Formal PASS is not determined by this structural check');
 const dif=entryCars.filter(x=>!cs.has(x));
 const nonNumeric=result.filter(x=>!/^\\d+$/.test(String(x.finishRaw??x.finish??''))).map(x=>({car:x.car,status:x.exceptionRaw||x.finishRaw||'UNSPECIFIED'}));
 return {raceKey:key,entryCount:entryCars.length||null,documentedResultRows:result.length,numericFinishers:numericFinishes.size,nonNumericResultRows:nonNumeric,missingFromResult:dif,officialStartersKnown:!!r.reconciliation?.revisedStartCardSource,errors,warnings,structuralOk:errors.length===0,publicationPassed:false};
}
if(require.main===module){
 const files=process.argv.slice(2);
 if(!files.length){console.error('Usage: node tools/reconcile_reconstructed_race.cjs path/to/research.json [...]');process.exit(2)}
 let fail=false;for(const p of files){try{const obj=JSON.parse(fs.readFileSync(p,'utf8'));const out=check(obj);console.log(JSON.stringify(out,null,2));if(out.errors.length)fail=true}catch(e){console.error(p+': '+e.message);fail=true}}
 if(fail)process.exitCode=1;
}
module.exports={check};
