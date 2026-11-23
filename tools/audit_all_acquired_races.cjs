#!/usr/bin/env node
'use strict';
// Read-only: audit all acquired research candidates and legacy comparison races.
// Never grants PASS or writes to official feeds. No undocumented official original assumed.
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const data=rel=>JSON.parse(fs.readFileSync(path.join(root,rel),'utf8'));
const norm=x=>String(x??'').normalize('NFKC').replace(/[\s\u3000]/g,'');
const numeric=x=>Number.isInteger(Number(x))&&Number(x)>0;
function inspectSourceFirst(r){
 const blockers=[],warnings=[],res=Array.isArray(r.results)?r.results:[],entries=Array.isArray(r.originalEntries)?r.originalEntries:[],resultCars=res.map(x=>Number(x.car)),lineCars=(r.preRaceFormation?.groups||[]).flat().map(Number);
 const hasFinishRaw=res.every(x=>Object.prototype.hasOwnProperty.call(x,'finishRaw'));
 const rank=x=>x.finishRaw??x.finish??x.exceptionRaw??'';
 const numericRows=res.filter(x=>/^\d+$/.test(String(rank(x))));
 const exceptionRows=res.filter(x=>!/^\d+$/.test(String(rank(x))));
 const nums=numericRows.map(x=>Number(rank(x)));
 if(![7,9].includes(res.length))blockers.push('RESULT_ROW_COUNT_UNEXPECTED');
 if(new Set(resultCars).size!==res.length)blockers.push('DUPLICATE_CAR');
 if(new Set(nums).size!==nums.length)blockers.push('DUPLICATE_NUMERIC_RANK');
 if(res.some(x=>!norm(x.name)))blockers.push('MISSING_RIDER_IDENTITY');
 if(entries.length===0)blockers.push('ORIGINAL_ENTRY_CARD_NOT_STRUCTURED');
 else{
  const cards=entries.map(x=>Number(x.car));
  if(new Set(cards).size!==entries.length)blockers.push('DUPLICATE_ENTRY_CAR');
  if(entries.some(x=>!resultCars.includes(Number(x.car)))||res.some(x=>!cards.includes(Number(x.car))))blockers.push('ENTRY_RESULT_CAR_MISMATCH_CHECK_OFFICIAL_WITHDRAWALS');
 }
 if(lineCars.length!==res.length||new Set(lineCars).size!==res.length||resultCars.some(x=>!lineCars.includes(x)))blockers.push('FORECAST_CAR_COVERAGE_MISMATCH');
 if(!hasFinishRaw)warnings.push('LEGACY_FINISH_RAW_MISSING_NORMALIZE_WITHOUT_INVENTING');
 if(!r.reconciliation?.revisedStartCardSource)warnings.push('OFFICIAL_AMENDED_ENTRY_NOT_RETRIEVED');
 const missingLap=numericRows.filter(x=>x.lapSeconds===null||x.lapSeconds===undefined||x.lapSeconds==='').map(x=>Number(x.car));
 if(missingLap.length)blockers.push('NUMERIC_FINISHER_LAP_NOT_DISPLAYED cars='+missingLap.join(','));
 const missingSBSource=res.filter(x=>x.sbDiscrepancy).map(x=>Number(x.car));
 if(missingSBSource.length)blockers.push('SOURCE_SB_MARKER_CONFLICT cars='+missingSBSource.join(','));
 const exception=exceptionRows.map(x=>({car:Number(x.car),sourceRaw:String(rank(x)),sourceExceptionRaw:String(x.exceptionRaw??'')}));
 if(exception.length)warnings.push('Nonnumeric source exception categories require original-rule mapping; do not fabricate ranks');
 if(!r.reconciliation?.revisedStartCardSource)blockers.push('OFFICIAL_ORGANIZER_PRIMARY_NOT_CAPTURED');
 if(!r.originalEntries?.length&&entries.length===0)warnings.push('Legacy source-first candidate needs original card transcription');
 if(!Array.isArray(r.resultUrls)||r.resultUrls.length<2)blockers.push('TWO_RESULT_PUBLICATIONS_NOT_RECORDED');
 blockers.push('UPSTREAM_ORIGIN_AND_PER_FIELD_QUALIFICATION_PENDING');
 return {key:r.raceKey,type:'source_first',venue:r.race?.venue,documentedRows:res.length,numericFinishers:numericRows.length,exceptionRows:exception,originalEntriesStructured:entries.length,formationCars:lineCars.length,resultPublisherUrls:r.resultUrls?.length||0,blockers:[...new Set(blockers)],warnings,status:'AUDITED_RESEARCH_PENDING',publicationPassed:false};
}
function inspectLegacy(r){
 const b=[],warnings=[],rows=r.finishers||[],cars=rows.map(x=>Number(x.number)),forecast=(r.formation?.groups||[]).flat().map(Number);
 if(![7,9].includes(rows.length)||new Set(cars).size!==rows.length)b.push('LEGACY_RESULT_ROW_OR_DUPLICATE_CAR');
 if(forecast.length!==rows.length||new Set(forecast).size!==rows.length||cars.some(x=>!forecast.includes(x)))b.push('LEGACY_FORECAST_CAR_COVERAGE');
 if(!Array.isArray(r.resultEvidenceByField)||r.resultEvidenceByField.length!==rows.length)b.push('PER_RIDER_PER_FIELD_SOURCE_RECEIPTS_NOT_STRUCTURED');
 if(!r.officialVerification?.sourceUrl)b.push('OFFICIAL_ORGANIZER_PRIMARY_NOT_CAPTURED');
 if(!r.originalEntries)b.push('ORIGINAL_ENTRY_CARD_NOT_STRUCTURED');
 if(!r.resultVerifiedDate&&!r.officialVerification?.verifiedDate)b.push('ORIGINAL_RESULT_OBSERVATION_DATE_NOT_STRUCTURED');
 if(r.resultLimitations)warnings.push('Legacy original limitations preserved, including optional payout notes');
 b.push('UPSTREAM_ORIGIN_QUALIFICATION_PENDING');
 return{key:r.key,type:'legacy_comparison',venue:r.track,documentedRows:rows.length,numericFinishers:rows.filter(x=>/^\d+$/.test(String(x.finish))).length,originalEntriesStructured:r.originalEntries?.length||0,formationCars:forecast.length,resultPublisherUrls:r.resultSourcePair?.length||0,blockers:[...new Set(b)],warnings,status:'AUDITED_RESEARCH_PENDING',publicationPassed:false};
}
function auditAll(sourceFirst,comparison){
 const races=sourceFirst.map(inspectSourceFirst).concat(comparison.races.map(inspectLegacy));
 const original=new Map(),linkedEvidencePairs=[];
 for(const r of sourceFirst.concat(comparison.races)){
  const key=r.raceKey||r.key;
  if(!original.has(key)){original.set(key,r);continue}
  const previous=original.get(key);
  const first=previous.raceKey?previous:r.raceKey?r:null;
  const legacy=previous.finishers?previous:r.finishers?r:null;
  // Only allow one formal PASS evidenced research JSON + one legacy receipt for the same race.
  // All other duplicated source-first or legacy keys remain a hard error.
  if(!first||!legacy||first.audit?.publicationPass!==true||legacy.formalPublication?.status!=='PASS'||legacy.formalPublication.key!==key||!Array.isArray(first.results)||!Array.isArray(legacy.finishers))throw Error('DUPLICATE_RACE_KEYS across research sources');
  const firstByCar=new Map(first.results.map(x=>[Number(x.car),[String(x.finishRaw??x.finish),norm(x.name)]]));
  const consistent=first.results.length===legacy.finishers.length&&firstByCar.size===first.results.length&&legacy.finishers.every(x=>{const value=firstByCar.get(Number(x.number));return value&&value[0]===String(x.finish)&&value[1]===norm(x.name)});
  if(!consistent)throw Error('DUPLICATE_RACE_KEYS conflicting rider rows');
  linkedEvidencePairs.push({key,types:['source_first','legacy_comparison'],proof:'formal publication and matching seven/nine original car/finish/name records',countAsNewRace:false});
 }
 return{schema:'ki-all-acquired-race-evidence-audit-v1',publicationDecision:'NO_PASS_OR_FEED_WRITE',summary:{sourceFirst:sourceFirst.length,legacyComparisons:comparison.races.length,allRaces:original.size,evidenceRecords:races.length,linkedExistingEvidencePairs:linkedEvidencePairs.length,resultRows:races.reduce((n,r)=>n+r.documentedRows,0),withNonnumericExceptions:races.filter(x=>x.exceptionRows?.length).length,sourceFirstWithoutStructuredOriginalEntry:sourceFirst.filter(r=>!r.originalEntries?.length).length,formalPass:0},linkedEvidencePairs,races};
}
if(require.main===module){
 const dir=path.join(root,'tools','reconstruction-candidates');
 const files=fs.readdirSync(dir).filter(x=>x.endsWith('.research.json')).sort();
 const all=files.map(f=>JSON.parse(fs.readFileSync(path.join(dir,f),'utf8')));
 const report=auditAll(all,data('comparison-races-v1.json'));
 console.log(JSON.stringify(report,null,2));
}
module.exports={auditAll,inspectSourceFirst,inspectLegacy};
