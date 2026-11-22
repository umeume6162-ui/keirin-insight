#!/usr/bin/env node
'use strict';
// Read-only guard: compare audited published source transcriptions with stored legacy races.
// Keeps external-source matches separate from independent official PASS.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base=path.resolve(__dirname,'..'),legacy=JSON.parse(fs.readFileSync(path.join(base,'comparison-races-v1.json'),'utf8'));
const norm=x=>String(x??'').normalize('NFKC').replace(/[\s\u3000]/g,'');
const method=x=>({'逃':'逃げ','差':'差し','ク':'マーク'}[norm(x)]||norm(x));
const margin=x=>norm(x).replace('タイヤ差','タイヤ');
function checkReceipt(receipt,races=legacy.races){
 const original=races.find(x=>x.key===receipt.raceKey),errors=[];
 if(!original)errors.push('unknown race key');
 const rows=receipt.transcribedRows??receipt.sourceTranscribedRows;
 if(!Array.isArray(rows))return{raceKey:receipt.raceKey,errors:['missing transcription rows'],publicationPassed:false};
 const byCar=new Map(original?.finishers?.map(x=>[Number(x.number),x])||[]);
 if(byCar.size!==rows.length)errors.push('result rider count differs');
 const seen=new Set();let compared=0;
 for(const row of rows){
  const car=Number(row.car),orig=byCar.get(car);
  if(seen.has(car))errors.push('duplicate car '+car);
  seen.add(car);
  if(!orig){errors.push('missing car '+car);continue;}
  const tests=[['finish',String(row.finish),String(orig.finish)],['name',norm(row.name),norm(orig.name)],['lap',Number(row.lapSeconds),Number(orig.lastLap)],['margin',margin(row.marginRaw),margin(orig.margin)],['method',method(row.winningMethodRaw),method(orig.winningMethod)],['SB',norm(row.sbRaw),norm(orig.startBack)]];
  if(Object.hasOwn(row,'prefecture'))tests.push(['prefecture',norm(row.prefecture),norm(orig.prefecture)]);
  if(Object.hasOwn(row,'period'))tests.push(['period',Number(row.period),Number(orig.period)]);
  if(Object.hasOwn(row,'grade'))tests.push(['grade',norm(row.grade),norm(orig.riderClass)]);
  for(const [field,a,b] of tests){compared++;if(a!==b)errors.push('car '+car+' '+field+' mismatch');}
 }
 const expected=receipt.summary?.fieldComparisons??receipt.summary?.normalizedComparisons;
 if(expected!==compared)errors.push('comparison count differs: '+compared+' vs '+expected);
 if(!Array.isArray(receipt.sources)&&!Array.isArray(receipt.transcriptionSourceSites))errors.push('no source evidence');
 if(receipt.publicationStatus==='OFFICIAL_PASS')errors.push('research receipt must not assert official PASS');
 return{raceKey:receipt.raceKey,compared,errors,allMatched:errors.length===0,publicationPassed:false};
}
if(require.main===module){
 const names=['2026-10-05_75_1.recheck.json','2026-10-05_75_2.recheck.json'],output=[];
 for(const n of names){const record=JSON.parse(fs.readFileSync(path.join(__dirname,'source-origin-audits',n),'utf8'));const v=checkReceipt(record);output.push(v);}
 console.log(JSON.stringify({schema:'ki-legacy-recheck-validation-v1',records:output,publicationPassed:false},null,2));
 if(output.some(x=>!x.allMatched))process.exitCode=1;
}
module.exports={checkReceipt};
