(()=>{
 const viewer=document.getElementById('storyViewer'); if(!viewer)return;
 const slides=[...viewer.querySelectorAll('.story-slide')]; if(!slides.length)return;
 const csrf=document.querySelector('meta[name="csrf-token"]')?.content||'';
 const start=Math.max(0,Math.min(slides.length-1,Number(document.body.dataset.startIndex||0)));
 let current=start,timer=null,started=0,remaining=5000,paused=false,muted=true;
 let programmaticScroll=false;

 const media=(s)=>s.querySelector('video,audio.story-music,.story-audio-card audio');
 function postView(s){fetch(`/api/story-view/${s.dataset.storyId}/`,{method:'POST',headers:{'X-CSRFToken':csrf}}).catch(()=>{});}
 function stopMedia(){slides.forEach(s=>s.querySelectorAll('video,audio').forEach(m=>{m.pause();try{m.currentTime=0}catch{}}));}
 function durationFor(s){const v=s.querySelector('video,.story-audio-card audio');return v&&Number.isFinite(v.duration)&&v.duration>0?Math.min(Math.max(v.duration*1000,2500),15000):5000;}
 function setSound(s){s.querySelectorAll('video,audio').forEach(m=>m.muted=muted);const b=s.querySelector('.story-sound');if(b)b.textContent=muted?'⌁':'◉';}
 function progress(s,ms){const bar=s.querySelector('.story-progress span');if(!bar)return;bar.style.transition='none';bar.style.width='0';requestAnimationFrame(()=>{bar.style.transition=`width ${ms}ms linear`;bar.style.width='100%';});}
 function clear(){if(timer){clearTimeout(timer);timer=null}}

 function preloadNext(i){
  if(slides[i+1]){
   const img=slides[i+1].querySelector('img[src]');
   if(img){const p=new Image();p.src=img.src;}
  }
 }

 function play(i){
  clear();stopMedia();
  current=Math.max(0,Math.min(slides.length-1,i));
  const s=slides[current];
  programmaticScroll=true;
  viewer.scrollTo({left:current*viewer.clientWidth,behavior:'smooth'});
  setTimeout(()=>{programmaticScroll=false;},350);
  postView(s);setSound(s);
  const m=media(s);if(m){m.play().catch(()=>{});}
  remaining=durationFor(s);started=performance.now();
  progress(s,remaining);
  timer=setTimeout(next,remaining);
  paused=false;
  preloadNext(current);
 }

 function next(){if(current<slides.length-1)play(current+1);else location.href='/child/dashboard/'}
 function prev(){if(current>0)play(current-1);else play(0)}

 function pause(){
  if(paused)return;paused=true;clear();
  remaining=Math.max(250,remaining-(performance.now()-started));
  const s=slides[current];s.querySelectorAll('video,audio').forEach(m=>m.pause());
  const bar=s.querySelector('.story-progress span');
  if(bar){const w=getComputedStyle(bar).width;bar.style.transition='none';bar.style.width=w;}
 }

 function resume(){
  if(!paused)return;paused=false;
  const s=slides[current];s.querySelectorAll('video,audio').forEach(m=>m.play().catch(()=>{}));
  started=performance.now();
  const bar=s.querySelector('.story-progress span');
  if(bar){bar.style.transition=`width ${remaining}ms linear`;bar.style.width='100%';}
  timer=setTimeout(next,remaining);
 }

 slides.forEach((s,i)=>{
  s.querySelector('.story-zone-left')?.addEventListener('click',prev);
  s.querySelector('.story-zone-right')?.addEventListener('click',next);
  s.querySelector('.story-sound')?.addEventListener('click',()=>{muted=!muted;setSound(s)});
  const stage=s.querySelector('[data-story-stage]');
  let hold;
  stage?.addEventListener('pointerdown',()=>{hold=setTimeout(pause,170)});
  ['pointerup','pointercancel','pointerleave'].forEach(ev=>stage?.addEventListener(ev,()=>{clearTimeout(hold);resume()}));
 });

 let settle;
 viewer.addEventListener('scroll',()=>{
  if(programmaticScroll)return;
  clearTimeout(settle);
  settle=setTimeout(()=>{
   const i=Math.round(viewer.scrollLeft/viewer.clientWidth);
   if(i!==current)play(i);
  },90);
 },{passive:true});

 window.addEventListener('resize',()=>viewer.scrollLeft=current*viewer.clientWidth);
 requestAnimationFrame(()=>{viewer.scrollLeft=start*viewer.clientWidth;play(start)});
})();
