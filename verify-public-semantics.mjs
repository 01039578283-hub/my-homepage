/** Fail the release on regressions in crawlable HTML and source-backed branch facts. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const output=path.join(root,'.public-release');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'release-public-manifest.json'),'utf8'));
const names=new Set(Object.keys(manifest.files));
const centers=JSON.parse(fs.readFileSync(path.join(root,'tools/data/branch-directory/branches.json'),'utf8')).centers;
const branches=new Map(centers.map(c=>[decodeURI(`https://wawa-center.kr/지점안내/${c.region}/${c.routeName}/#academy`),c]));
const decode=s=>s.replace(/&(?:amp|quot|apos|lt|gt|#39);/g,x=>({'&amp;':'&','&quot;':'"','&apos;':"'",'&lt;':'<','&gt;':'>','&#39;':"'"}[x]));
const attrs=s=>Object.fromEntries([...s.matchAll(/([\w:-]+)\s*=\s*(["'])([\s\S]*?)\2/g)].map(m=>[m[1].toLowerCase(),decode(m[3])]));
const types=n=>Array.isArray(n['@type'])?n['@type']:[n['@type']];
function* walk(n){if(Array.isArray(n)){for(const v of n)yield*walk(v);}else if(n&&typeof n==='object'){yield n;for(const v of Object.values(n))yield*walk(v);}}
const resolve=p=>{const n=decodeURIComponent(p).replace(/^\//,'');return [n,n?n.replace(/\/$/,'')+'/index.html':'index.html',n+'.html'].find(x=>names.has(x));};
let pages=0,branchNodes=0;const errors=[];
const pageNames=[...names].filter(name=>name.endsWith('.html')&&!name.startsWith('assets/'));
let cursor=0;
await Promise.all(Array.from({length:12},async()=>{while(cursor<pageNames.length){
 const name=pageNames[cursor++];
 const s=await fs.promises.readFile(path.join(output,name),'utf8');
 const canonical=[...s.matchAll(/<link\b[^>]*>/gi)].map(m=>attrs(m[0])).filter(a=>a.rel==='canonical');
 if(canonical.length!==1){errors.push([name,'canonical count']);continue;}
 const url=canonical[0].href;pages++;
 if((s.match(/<title\b/gi)||[]).length!==1)errors.push([name,'title count']);
 const metadata=[...s.matchAll(/<meta\b[^>]*>/gi)].map(m=>attrs(m[0]));
 const desc=metadata.filter(m=>m.name==='description');
 if(desc.length!==1||!desc[0].content||[...desc[0].content].length>80)errors.push([name,'description']);
 if(metadata.some(m=>['robots','googlebot','naverbot','yeti'].includes(m.name?.toLowerCase())&&/noindex/i.test(m.content)))errors.push([name,'noindex']);
 for(const m of s.matchAll(/<(?:img|script|link|a)\b[^>]*>/gi)){
  const a=attrs(m[0]);
  if(/^<img\b/i.test(m[0])&&!('alt' in a))errors.push([name,'missing image alt']);
  const target=a.src||a.href;
  if(!target)continue;
  try{const u=new URL(target,url);if(u.hostname==='wawa-center.kr'&&!resolve(u.pathname))errors.push([name,'missing local destination',target]);}catch{errors.push([name,'invalid URL',target]);}
 }
 for(const m of s.matchAll(/<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)){
  try{for(const n of walk(JSON.parse(m[1]))){
   if('openingHoursSpecification' in n||'openingHours' in n)errors.push([name,'exact operating hours need verified source and visible content']);
   if(types(n).some(t=>t==='EducationalOrganization'||t==='LocalBusiness')&&n['@id']?.endsWith('#academy')){
    const c=branches.get(decodeURI(n['@id']));branchNodes++;
    if(!c||n.name!==c.displayName||n.address?.streetAddress!==c.address)errors.push([name,'branch entity differs from reviewed source']);
   }
  }}catch(e){errors.push([name,'JSON-LD',e.message]);}
 }
}}));
if(pages!==manifest.sitemapPages)errors.push(['page count',pages,manifest.sitemapPages]);
console.log(JSON.stringify({semanticValidation:true,pages,branchNodes,errors:errors.length,examples:errors.slice(0,12)}));
if(errors.length)process.exitCode=1;
