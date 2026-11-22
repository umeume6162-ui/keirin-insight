'use strict';
// Reconcile an archived pre-race entry list with all available result/status records.
// This is an intake aid, not independent web verification or a PASS decision.
function reconcile(entries, results) {
  if (!Array.isArray(entries) || !Array.isArray(results)) throw Error('arrays required');
  if (![7,9].includes(entries.length)) throw Error('expected 7 or 9 entrants');
  const digit=n=>Number.isInteger(Number(n)) && Number(n)>=1 && Number(n)<=9;
  const map=new Map();
  for(const e of entries){
    if(!digit(e.car)||!String(e.name||'').trim())throw Error('invalid entry identity');
    const car=Number(e.car);
    if(map.has(car))throw Error('duplicate entrant car');
    map.set(car,e);
  }
  const states=new Set(['欠車','取消','失格','落車棄権','途中棄権','棄権']);
  const seen=new Set(),numeric=[],exceptions=[],unresolved=[];
  for(const r of results){
    const car=Number(r.car);
    if(!map.has(car)||seen.has(car))throw Error('unknown/duplicated result car');
    seen.add(car);
    if(r.name && r.name.replace(/\s|　/g,'')!==map.get(car).name.replace(/\s|　/g,''))throw Error('entry/result identity mismatch');
    const finish=String(r.finish??'').trim();
    if(/^\d+$/.test(finish)){
      numeric.push({car,finish:Number(finish),incident:r.incident||null});
    }else if(states.has(finish)){
      const sites=Array.isArray(r.statusSourceDomains)?new Set(r.statusSourceDomains):new Set();
      if(sites.size>=2) exceptions.push({car,status:finish});
      else unresolved.push({car,reason:'exception status lacks two independent sources'});
    }else{
      unresolved.push({car,reason:'unresolved finish status'});
    }
  }
  if(new Set(numeric.map(x=>x.finish)).size!==numeric.length)throw Error('duplicate finish rank');
  const missing=[...map.keys()].filter(c=>!seen.has(c));
  for(const car of missing) unresolved.push({car,reason:'missing result/status row; check another result source'});
  return {expectedEntrants:entries.length,receivedRows:results.length,numericFinishers:numeric.length,confirmedExceptions:exceptions.length,missingCars:missing,numeric,exceptions,unresolved,readyForFieldVerification:unresolved.length===0&&numeric.length+exceptions.length===entries.length};
}
module.exports={reconcile};
if(require.main===module){
 const assert=require('node:assert/strict');
 const entries=Array.from({length:7},(_,i)=>({car:i+1,name:'選手'+(i+1)}));
 const full=Array.from({length:7},(_,i)=>({car:i+1,name:'選手'+(i+1),finish:i+1}));
 assert.equal(reconcile(entries,full).readyForFieldVerification,true);
 const six=reconcile(entries,full.slice(0,6));
 assert.deepEqual(six.missingCars,[7]);assert.equal(six.readyForFieldVerification,false);
 const recovered=reconcile(entries,[...full.slice(0,6),{car:7,name:'選手7',finish:'失格',statusSourceDomains:['keirin.jp','winticket.jp']}]);
 assert.equal(recovered.confirmedExceptions,1);assert.equal(recovered.readyForFieldVerification,true);
 assert.equal(reconcile(entries,[...full.slice(0,6),{car:7,finish:'失格',statusSourceDomains:['keirin.jp']}]).readyForFieldVerification,false);
 assert.throws(()=>reconcile(entries,[...full.slice(0,6),{car:7,finish:6}]),/duplicate finish rank/);
 assert.throws(()=>reconcile(entries,[...full.slice(0,6),{car:7,name:'他人',finish:7}]),/identity mismatch/);
 console.log('OK: complete 7-car, incomplete 6-car, verified exception rescue, single-source hold, duplicate rank, identity mismatch');
}
