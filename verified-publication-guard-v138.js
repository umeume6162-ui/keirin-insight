(()=>{'use strict';const guest=(race,n,name)=>{const list=race?.invitedRiders;if(!Array.isArray(list))return false;const p=list.find(x=>Number(x.number)===Number(n));const norm=v=>String(v??'').replace(/[\s\u3000]/g,'');return !!p&&p.kind==='foreign_invited'&&!!norm(name)&&norm(p.name)===norm(name)&&norm(p.entryName)===norm(name)&&/^https:\/\//.test(String(p.entryUrl||''))&&/^https:\/\//.test(String(p.statusSourceUrl||''))&&typeof p.evidenceRef==='string'&&p.evidenceRef.trim().length>8};
function verifyPublication(a,b,i,l){
 const fail=m=>{throw Error('掲載検査：'+m)},norm=x=>String(x??'').replace(/[\s\u3000]/g,''),date=x=>/^\d{4}-\d{2}-\d{2}$/.test(String(x??'')),official=u=>/^https:\/\/(?:www\.)?keirin\.jp\//.test(String(u??'')),idurl=(u,id)=>/^https:\/\//.test(String(u??''))&&String(u).includes(String(id)),evidence=x=>x?.officialVerification?.status==='verified'&&date(x.verifiedDate)&&x.officialVerification?.method==='two_distinct_sites_agree'&&Array.isArray(x.officialVerification.matchingSources)&&new Set(x.officialVerification.matchingSources.map(u=>{try{return new URL(u).hostname.replace(/^www\./,'')}catch{return ''}})).size>=2&&x.officialVerification.matchingSources.every(u=>/^https:\/\//.test(String(u)));
 const kdSource=u=>/^https:\/\/keirin\.kdreams\.jp\//.test(String(u??''));
 const kdResult=x=>{const e=x?.officialVerification,p=e?.sourceProof;return e?.status==='verified'&&e?.method==='kdreams_single_source_verified'&&date(x.verifiedDate)&&kdSource(e.source)&&Array.isArray(e.matchingSources)&&e.matchingSources.length===1&&e.matchingSources[0]===e.source&&p&&['live_html','preserved_original_html'].includes(p.kind)&&date(p.retrievedDate)&&typeof p.evidenceRef==='string'&&p.evidenceRef.trim().length>8};
 const fallbackResult=x=>{const e=x?.officialVerification,p=e?.sourceProof;return e?.status==='verified'&&e?.method==='fallback_source_verified'&&date(x.verifiedDate)&&/^https:\/\/(?:www\.chariloto\.com\/keirin\/results\/|keirin\.netkeiba\.com\/race\/result\/)/.test(String(e.source||''))&&Array.isArray(e.matchingSources)&&e.matchingSources.length===1&&e.matchingSources[0]===e.source&&p?.kind==='live_html'&&p?.sourceTier==='other_media'&&date(p.retrievedDate)&&typeof p.evidenceRef==='string'&&p.evidenceRef.length>8&&/^https:\/\/github\.com\/.+\/actions\/runs\/\d+$/.test(String(p.runUrl||''))};
 const resultEvidence=x=>evidence(x)||kdResult(x)||fallbackResult(x);
 const sourceHost=u=>String(u??'').match(/^https:\/\/(?:www\.)?([^/?#]+)/)?.[1]||'',twoSites=x=>{const e=x?.officialVerification;if(e?.method!=='two_distinct_sites_agree'||!Array.isArray(e.matchingSources)||e.matchingSources.length<2)return false;const hosts=new Set(e.matchingSources.map(sourceHost));return hosts.size>=2&&!hosts.has('')&&e.matchingSources.some(u=>idurl(u,x.id))&&['name','prefecture','period','id'].every(k=>e.fields?.includes(k))};
 const sameSourceUrl=(a,b)=>{try{const x=new URL(a),y=new URL(b);return x.protocol==='https:'&&y.protocol==='https:'&&x.hostname.replace(/^www\./,'')===y.hostname.replace(/^www\./,'')&&x.pathname===y.pathname&&x.search===y.search}catch{return false}};
 const riderEvidence=x=>x?.officialVerification?.status==='verified'&&date(x.verifiedDate)&&/^https:\/\//.test(String(x.source??''))&&/^https:\/\//.test(String(x.officialVerification.source??''));
 const ids=new Set(),persons=new Set(),keys=new Map(),seen=new Set(),counts=new Map();
 for(const x of i.riders){const p=norm(x.prefecture),k=[norm(x.name),({'神奈川':'神奈','北海道':'北海','和歌山':'和歌'}[p]||p),String(x.period)].join('|');if(!twoSites(x)||!riderEvidence(x)||!x.officialVerification.matchingSources.some(u=>sameSourceUrl(u,x.source))||!x.officialVerification.matchingSources.some(u=>sameSourceUrl(u,x.officialVerification.source))||!norm(x.name)||!p||!/^\d+$/.test(x.period)||!Array.isArray(x.officialVerification.fields)||!['name','prefecture','period','id'].every(f=>x.officialVerification.fields.includes(f))||ids.has(x.id)||persons.has(k))fail('選手ID・照合根拠・重複');ids.add(x.id);persons.add(k)}
 for(const x of a.races){const k=[x.date,String(x.track_code),Number(x.race)].join('|');if(!resultEvidence(x)||!date(x.date)||!x.track||!Number.isInteger(Number(x.race))||Number(x.race)<1||Number(x.race)>12||![7,9].includes(x.size)||keys.has(k))fail('レース照合根拠・識別キー');keys.set(k,x)}
 const required=['date','track','trackCode','race','number','name','prefecture','period','finishRaw','riderClass','sourceUrl'];if(!Array.isArray(b.columns)||new Set(b.columns).size!==b.columns.length||required.some(k=>!b.columns.includes(k)))fail('必須列');
 const pos=Object.fromEntries(b.columns.map((x,n)=>[x,n]));for(const row of b.rows){if(!Array.isArray(row)||row.length!==b.columns.length)fail('出走行形式');const get=k=>row[pos[k]],k=[get('date'),String(get('trackCode')),Number(get('race'))].join('|'),r=keys.get(k),n=Number(get('number')),rk=k+'|'+n;if(!r||get('track')!==r.track||!Number.isInteger(n)||n<1||n>9||!norm(get('name'))||(!guest(r,n,get('name'))&&(!norm(get('prefecture'))||!/^\d+$/.test(String(get('period')))||!norm(get('riderClass'))))||!norm(get('finishRaw'))||!/^https:\/\//.test(String(get('sourceUrl')))||!r.officialVerification.matchingSources.includes(get('sourceUrl'))||seen.has(rk))fail('出走行の照合・重複');seen.add(rk);counts.set(k,(counts.get(k)||0)+1)}
 for(const [k,r] of keys)if(counts.get(k)!==r.size)fail('レース別人数');
 for(const [k,r] of keys)if(kdResult(r)){const rows=b.rows.filter(row=>[row[pos.date],String(row[pos.trackCode]),Number(row[pos.race])].join('|')===k);if(!rows.every(row=>kdSource(row[pos.sourceUrl])&&row[pos.sourceUrl]===r.officialVerification.source))fail('Kドリームス単一原本・全車URL不一致');}
 for(const [k,r] of keys)if(fallbackResult(r)){const rows=b.rows.filter(row=>[row[pos.date],String(row[pos.trackCode]),Number(row[pos.race])].join('|')===k);if(!rows.every(row=>row[pos.sourceUrl]===r.officialVerification.source))fail('代替原文・全車URL不一致');}
 const forecastSource=x=>{const e=x?.officialVerification,p=e?.sourceProof;return e?.status==='verified'&&e?.method==='published_single_source_forecast'&&date(x.verifiedDate)&&e?.forecastType==='media_prediction'&&typeof e.source==='string'&&/^https:\/\//.test(e.source)&&Array.isArray(e.matchingSources)&&e.matchingSources.length===1&&e.matchingSources[0]===e.source&&p?.kind==='published_pre_race_forecast'&&date(p.retrievedDate)&&typeof p.evidenceRef==='string'&&p.evidenceRef.trim().length>8&&typeof p.provider==='string'&&p.provider.trim().length>0};
 const sameName=(x,y)=>norm(x)===norm(y);
 const lineKeys=new Set();for(const x of l.races){
  const e=x.officialVerification;
  if(!(evidence(x)||forecastSource(x)||(kdResult(x)&&e?.method==='kdreams_single_source_verified'))||!date(x.date)||!x.track||!/^\d{2}$/.test(String(x.trackCode||''))||!Number.isInteger(Number(x.race))||Number(x.race)<1||Number(x.race)>12||!x.id||x.id!==[x.date,String(x.trackCode),Number(x.race)].join('|')||lineKeys.has(x.id)||!Array.isArray(x.riders)||![7,9].includes(x.riders.length)||x.size!==x.riders.length)fail('ライン予想の出典・レース識別・重複');
  lineKeys.add(x.id);
  const groups=contestedGroups(x)||x.forecastGroups;
  if(x.lineMode!==undefined&&!['no_line','line','contested'].includes(x.lineMode))fail('競走形式不明');
  if(x.lineMode==='no_line'&&(!(x.lineMode==='no_line'&&['girls','advance','other_individual'].includes(x.raceFormat)&&typeof x.originalFormation==='string'&&x.originalFormation.trim().length>0&&typeof x.formatEvidenceUrl==='string'&&/^https:\/\//.test(x.formatEvidenceUrl))||!Array.isArray(groups)||groups.some(q=>!Array.isArray(q)||q.length!==1)))fail('ラインなし競走の証拠・全車独立不備');
  if(!Array.isArray(groups)||!groups.length||groups.some(g=>!Array.isArray(g)||!g.length)||groups.flat().length!==x.size)fail('ライン全車グループ不備');
  const nums=groups.flat().map(Number),expected=Array.from({length:x.size},(_,i)=>i+1);
  if(new Set(nums).size!==x.size||nums.some(n=>!Number.isInteger(n))||nums.slice().sort((a,b)=>a-b).join(',')!==expected.join(','))fail('ライン車番の不足・重複');
  if(new Set(x.riders.map(r=>Number(r.number))).size!==x.size)fail('ライン選手の重複');
  for(const rider of x.riders){
   const n=Number(rider.number),grp=groups.find(g=>g.map(Number).includes(n));
   if(!Number.isInteger(n)||!grp||!sameName(rider.name,rider.name)||!norm(rider.name)||(!guest(x,n,rider.name)&&(!norm(rider.prefecture)||!/^\d+$/.test(String(rider.period))))||(x.lineMode!=='contested'&&(!Array.isArray(rider.line)||rider.line.map(Number).join(',')!==grp.map(Number).join(','))))fail('ライン選手・グループ不整合');
  }
  const connected=keys.get(x.id);
  if(connected){
   if(connected.size!==x.riders.length||connected.track!==x.track)fail('ライン結果レース不一致');
   const linkedRows=b.rows.filter(row=>[row[pos.date],String(row[pos.trackCode]),Number(row[pos.race])].join('|')===x.id);
   for(const rider of x.riders){
    const row=linkedRows.find(row=>Number(row[pos.number])===Number(rider.number));
    if(!row||!sameName(row[pos.name],rider.name)||(!(guest(connected,rider.number,row[pos.name])&&guest(x,rider.number,rider.name))&&(!sameName(row[pos.prefecture],rider.prefecture)||String(row[pos.period])!==String(rider.period))))fail('ライン・結果選手の本人不一致');
   }
  }
 }
 if(l.summary?.rider_rows!==l.races.reduce((n,x)=>n+x.riders.length,0))fail('ライン人数');
}
const originalFetch=window.fetch.bind(window);
const names=['results','rider-results','rider-ids','line-snapshots'];
const files=names.map(k=>'verified-'+k+'-feed-v1.json');
let inflight=null,cache=null,checked=0;
async function bundle(){if(cache&&Date.now()-checked<15000)return cache;if(inflight)return inflight;inflight=(async()=>{const [a,b,i,l]=await Promise.all(files.map(async f=>{const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);try{const r=await originalFetch('./'+f,{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error(f+' HTTP '+r.status);const j=await r.json();if(j.publicationPolicy!=='ki-verified-only-v1')throw Error('掲載基準不一致');return j}finally{clearTimeout(timer)}}));if(a.schema!=='ki-public-results-index-v1'||b.schema!=='ki-rider-results-v1'||i.schema!=='ki-official-rider-ids-v1'||l.schema!=='ki-line-snapshots-v1'||!Array.isArray(a.races)||!Array.isArray(b.rows)||!Array.isArray(i.riders)||!Array.isArray(l.races)||a.source_snapshot_date!==b.snapshotDate||a.latest_race_date!==b.latestEventDate||a.summary?.races!==a.races.length||b.summary?.races!==a.races.length||a.summary?.rider_rows!==b.rows.length||b.summary?.rows!==b.rows.length||i.summary?.rows!==i.riders.length||l.summary?.races!==l.races.length||a.races.reduce((n,r)=>n+r.size,0)!==b.rows.length)throw Error('配信データ整合性不成立'); verifyPublication(a,b,i,l);cache=[a,b,i,l];checked=Date.now();return cache})().catch(e=>{cache=null;checked=0;throw e}).finally(()=>{inflight=null});return inflight}
const contestedGroups=x=>{
 if(x.lineMode!=='contested')return null;
 if(typeof x.originalFormation!=='string'||!Array.isArray(x.forecastSlots)||!x.forecastSlots.length||!/^https:\/\//.test(String(x.formatEvidenceUrl||''))||!x.officialVerification?.matchingSources?.includes(x.formatEvidenceUrl))throw Error('競り原文・出典不備');
 const groups=x.forecastSlots;
 if(groups.some(g=>!Array.isArray(g)||!g.length||Array.isArray(g[0])||g.some(v=>Array.isArray(v)?v.length<2||v.some(n=>!Number.isInteger(n)||n<1||n>x.size):!Number.isInteger(v)||v<1||v>x.size))||!groups.some(g=>g.some(Array.isArray)))throw Error('競り位置不備');
 const raw=x.originalFormation.replace(/[①②③④⑤⑥⑦⑧⑨]/g,c=>String('①②③④⑤⑥⑦⑧⑨'.indexOf(c)+1)).normalize('NFKC').replace(/\s/g,'');
 const canonical=groups.map(g=>g.map(v=>Array.isArray(v)?'('+v.join('')+')':String(v)).join('')).join('/');
 if(raw!==canonical)throw Error('競り元表記不一致');
 if(x.forecastGroups!==undefined||x.riders.some(r=>r.line!==undefined&&r.line!==null))throw Error('競りを通常ラインに変換不可');
 return groups.map(g=>g.flat());
};
window.KIVerified={version:'13.8',bundle,validate:verifyPublication,guest,contestedGroups};
window.fetch=async function(input,init){let u;try{u=new URL(typeof input==='string'?input:input.url||String(input),location.href)}catch{return originalFetch(input,init)}const f=u.pathname.split('/').pop(),n=files.indexOf(f);if(n>=0&&u.origin===location.origin){const data=await bundle();return new Response(JSON.stringify(data[n]),{status:200,headers:{'Content-Type':'application/json'}})}if(/^(?:results|rider-results|rider-ids|line-snapshots)-feed-v1\.json$/.test(f)&&u.origin===location.origin)throw Error('未照合配信への接続は禁止されています');return originalFetch(input,init)};
})();