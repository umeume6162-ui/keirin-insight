"use strict";

function allLines(entries){
 // A pre-race source's complete car-group claims may be displayed only when
 // every rider is covered exactly once. Missing data is NOT a singleton.
 const known=entries.map(e=>Number(e.number)).sort((a,b)=>a-b);
 if(![7,9].includes(known.length)||new Set(known).size!==known.length)return null;
 const claims=entries.map(e=>String(e.preRaceLine||"").trim());
 if(claims.some(v=>!v))return null;
 const groups=new Map();
 for(let i=0;i<entries.length;i++){
  const tokens=claims[i]==="単騎"||claims[i]==="単独" ? [String(entries[i].number)] : claims[i].split(/[-－ー−–→＞>・\s]+/).filter(Boolean);
  if(!tokens.length||tokens.some(n=>!/^[1-9]$/.test(n)))return null;
  const cars=tokens.map(Number);
  if(new Set(cars).size!==cars.length||!cars.includes(Number(entries[i].number)))return null;
  const sorted=[...cars].sort((a,b)=>a-b).join(",");
  // Same group can appear in a different rider's record, with a
  // different order: that is a source conflict, not a confirmed line.
  const existing=groups.get(sorted);
  if(existing&&existing.join(",")!==cars.join(","))return null;
  groups.set(sorted,cars);
 }
 const result=[...groups.values()];
 const flattened=result.flat();
 if(flattened.length!==known.length||new Set(flattened).size!==known.length||flattened.sort((a,b)=>a-b).join(",")!==known.join(","))return null;
 return result;
}
