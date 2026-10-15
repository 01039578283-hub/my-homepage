/* Load the supplied map once it approaches the viewport. */
(()=>{'use strict';
const frames=[...document.querySelectorAll('iframe[data-kakao-src]')];
if(!frames.length)return;
function load(frame){
 if(frame.hasAttribute('src'))return;
 const surface=frame.closest('.kd-surface');
 const placeholder=surface?.querySelector('.kd-loading');
 frame.addEventListener('load',()=>{if(placeholder)placeholder.hidden=true;},{once:true});
 frame.loading='eager';
 frame.src=frame.dataset.kakaoSrc;
}
if(!('IntersectionObserver' in window)){frames.forEach(load);return;}
const observer=new IntersectionObserver(entries=>{
 for(const entry of entries)if(entry.isIntersecting){observer.unobserve(entry.target);load(entry.target);}
},{rootMargin:'300px 0px',threshold:0});
frames.forEach(frame=>observer.observe(frame));
})();
