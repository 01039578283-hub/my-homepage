/** Scoped presentation pass; source pages and original map snippets are retained. */
import fs from 'node:fs';
const config=JSON.parse(fs.readFileSync(new URL('./kakao-map-presentation.json',import.meta.url),'utf8'));
export const presentationStats={pages:0,sections:0,embeddedPages:0,hubs:0};
const frameUrls=new Set(Object.values(config.maps));
export function presentKakaoMapHTML(name,input,count=true){
 if(!name.endsWith('.html')||name.startsWith('assets/')||!input.includes('<!-- kakao-directions:style -->'))return input;
 if(!input.includes(config.oldCss)){
  if(input.includes(config.css))return input;
  throw Error('Unknown directions stylesheet: '+name);
 }
 let sections=0,embedded=0;
 let output=input.replace(/<!-- kakao-directions:start -->[\s\S]*?<!-- kakao-directions:end -->/g,section=>{
  sections++;
  section=section.replace(/<div class="kd-actions">[\s\S]*?<\/div>/g,'');
  section=section.replace(/<p class="kd-(?:kicker|intro|note)">[\s\S]*?<\/p>/g,'');
  section=section.replace(/<div class="kd-loading">[\s\S]*?<\/div>/g,'<div class="kd-loading" role="status"><p>지도를 불러오는 중입니다.</p></div>');
  section=section.replace(/<iframe class="kd-frame"/g,'<iframe class="kd-frame" sandbox="allow-scripts allow-same-origin"');
  const match=section.match(/data-kakao-src="([^"]+)"/);
  if(match){
   const target=config.maps[match[1]];
   if(!target&&!frameUrls.has(match[1]))throw Error('Unknown branch map: '+name);
   if(target)section=section.replaceAll(match[1],target);
   embedded++;
  }
  if(/<a\b/.test(section))throw Error('Unexpected navigation in directions: '+name);
  return section;
 });
 output=output.replace(config.oldCss,config.css).replace(config.oldJs,config.js);
 output=output.replace(/(<!-- kakao-directions:hub-link -->[\s\S]*?)지도·길찾기([\s\S]*?<!-- \/kakao-directions:hub-link -->)/g,'$1지도 보기$2');
 if(count){presentationStats.pages++;presentationStats.sections+=sections;presentationStats.embeddedPages+=embedded;if(!sections)presentationStats.hubs++;}
 return output;
}
export function verifyKakaoPresentationCounts(){
 for(const [key,expected] of Object.entries(config.expected))if(presentationStats[key]!==expected)throw Error('Directions presentation count differs: '+key+' '+presentationStats[key]+' / '+expected);
 return presentationStats;
}
