(()=>{
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  const csrf=()=>$('meta[name="csrf-token"]')?.content||'';

  async function postForm(url,data={}){
    const body=new URLSearchParams(data);
    const r=await fetch(url,{method:'POST',headers:{'X-CSRFToken':csrf(),'Content-Type':'application/x-www-form-urlencoded'},body});
    let j={};try{j=await r.json();}catch{}
    return {ok:r.ok,data:j,status:r.status};
  }
  const escapeHtml=v=>{const d=document.createElement('div');d.textContent=String(v??'');return d.innerHTML;};
  function showToast(message){
    const stack=document.querySelector('.toast-stack');if(!stack)return;
    const el=document.createElement('div');el.className='ln-toast';el.textContent=message;stack.appendChild(el);
    requestAnimationFrame(()=>el.classList.add('show'));setTimeout(()=>{el.classList.remove('show');setTimeout(()=>el.remove(),220);},1800);
  }
  // Shared with other page scripts (chat.js, feed_quiz.js, stories.js) so every
  // surface uses the same in-app toast instead of a blocking alert()/prompt().
  window.lnToast=showToast;

  $$('[data-language-select]').forEach(sel=>sel.addEventListener('change',()=>sel.form?.submit()));
  $$('[data-review-toggle]').forEach(btn=>btn.addEventListener('click',()=>{
    const panel=btn.closest('[data-review-card]')?.querySelector('[data-review-preview]');if(!panel)return;
    const revealed=panel.classList.toggle('revealed');panel.classList.toggle('blurred',!revealed);btn.setAttribute('aria-expanded',revealed?'true':'false');
    btn.innerHTML=revealed?'Hide flagged media':'Show flagged media';
  }));

  $$('img[data-hide-error]').forEach(img=>{
    const fallback=()=>{
      if(!img.dataset.fb){
        img.dataset.fb='1';
        img.src='/uploads/profile_pictures/download.webp';
      }
    };
    img.addEventListener('error',fallback);
  });

  function bindLike(root=document){
    $$('[data-like]',root).forEach(b=>{
      if(b.dataset.bound)return;b.dataset.bound='1';
      b.onclick=async()=>{const r=await postForm(`/like/${b.dataset.like}/`);if(r.ok){b.classList.toggle('liked',!!r.data.liked);b.setAttribute('aria-pressed',r.data.liked?'true':'false');const count=document.querySelector(`[data-like-count=\"${b.dataset.like}\"]`);if(count&&Number.isFinite(Number(r.data.likes)))count.textContent=String(r.data.likes);if(r.data.liked)showToast('Liked! 💛');}};
    });
  }

  function bindFollow(root=document){
    $$('[data-follow]',root).forEach(b=>{
      if(b.dataset.bound)return;b.dataset.bound='1';
      b.onclick=async()=>{
        const r=await postForm(`/follow/${b.dataset.follow}/`);
        if(r.ok){
          if(r.data.status==='pending'||r.data.status==='follow_back_pending'){
            b.textContent='Requested';
            b.classList.remove('ig-btn-primary');
            b.classList.add('ig-btn-secondary');
            showToast(r.data.status==='follow_back_pending'?'Follow request sent! Their parent still needs to approve. 🤝':'Follow request sent! 🤝');
          } else if(r.data.status==='removed'||r.data.status==='cancelled'){
            b.textContent='Follow';
            b.classList.remove('ig-btn-secondary');
            b.classList.add('ig-btn-primary');
            showToast(r.data.status==='cancelled'?'Request cancelled':'Connection removed');
          } else {
            b.textContent='Follow';
          }
        }
      };
    });
  }

  function openSheet(title, buildBody){
    const backdrop=document.createElement('div');backdrop.className='share-sheet-backdrop';
    const box=document.createElement('div');box.className='share-sheet';
    const h=document.createElement('h3');h.textContent=title;box.appendChild(h);
    const close=()=>backdrop.remove();
    buildBody(box,close);
    const cancel=document.createElement('button');cancel.className='btn';cancel.textContent='Cancel';cancel.onclick=close;box.appendChild(cancel);
    backdrop.appendChild(box);backdrop.onclick=e=>{if(e.target===backdrop)close();};document.body.appendChild(backdrop);
    return {backdrop,box,close};
  }

  async function share(postId){
    let friends=[];
    try{const r=await fetch('/api/following/',{cache:'no-store'});if(r.ok)friends=await r.json();}catch{}
    if(!friends.length){showToast('No approved connections available to share with.');return;}
    openSheet('Share with',(box)=>{
      for(const f of friends){
        const b=document.createElement('button');b.className='share-person';b.textContent=f.full_name;
        b.onclick=async()=>{
          const r=await fetch('/api/share-post/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({receiver_id:f.user_id,post_id:postId})});
          if(r.ok){b.textContent='Sent ✓';showToast('Shared! ✉️');}else showToast('Could not share this post.');
        };
        box.appendChild(b);
      }
    });
  }

  function bindShare(root=document){
    $$('[data-share-post]',root).forEach(b=>{if(b.dataset.bound)return;b.dataset.bound='1';b.onclick=()=>share(Number(b.dataset.sharePost));});
  }

  function bindSave(root=document){
    $$('[data-save-post]',root).forEach(b=>{
      if(b.dataset.bound)return;b.dataset.bound='1';
      b.onclick=async()=>{const r=await postForm(`/save/${b.dataset.savePost}/`);if(r.ok){b.classList.toggle('saved',!!r.data.saved);b.setAttribute('aria-pressed',r.data.saved?'true':'false');showToast(r.data.saved?'Saved for later':'Removed from saved');}};
    });
  }

  const REPORT_REASONS=['Bullying','Harassment','Unsafe content','Spam','Other'];

  function openReportSheet(targetType,targetId){
    let selected='';
    const {box,close}=openSheet('Report this content',(box)=>{
      const hint=document.createElement('p');hint.className='report-hint';hint.textContent='Choose the reason that fits best:';box.appendChild(hint);
      const list=document.createElement('div');list.className='report-reasons';
      REPORT_REASONS.forEach(reason=>{
        const rb=document.createElement('button');rb.type='button';rb.className='report-reason-btn';rb.textContent=reason;
        rb.onclick=()=>{selected=reason;$$('.report-reason-btn',list).forEach(x=>x.classList.remove('selected'));rb.classList.add('selected');};
        list.appendChild(rb);
      });
      box.appendChild(list);
      const submit=document.createElement('button');submit.className='btn btn-primary';submit.textContent='Submit report';
      submit.onclick=async()=>{
        if(!selected){showToast('Choose a reason first');return;}
        const r=await postForm('/report/',{target_type:targetType,target_id:targetId,reason:selected});
        showToast(r.ok?'Report sent to LittleNet safety review.':'Could not report this content.');
        close();
      };
      box.appendChild(submit);
    });
  }

  function bindReport(root=document){
    $$('[data-report-post]',root).forEach(b=>{
      if(b.dataset.bound)return;b.dataset.bound='1';
      b.onclick=()=>openReportSheet('POST',b.dataset.reportPost);
    });
  }

  function bindDouble(root=document){
    $$('[data-double-like]',root).forEach(el=>{
      if(el.dataset.doubleBound)return;el.dataset.doubleBound='1';let last=0;
      el.addEventListener('pointerup',async()=>{
        const now=Date.now();
        if(now-last<340){
          const h=$('.heart-burst',el);
          if(h){
            h.classList.remove('show');
            void h.offsetWidth;
            h.classList.add('show');
            setTimeout(()=>h.classList.remove('show'),600);
          }
          const b=document.querySelector(`[data-like="${el.dataset.doubleLike}"]`);
          if(b && !b.classList.contains('liked')){
            b.click();
          }
        }
        last=now;
      });
    });
  }

  function observeVideos(root=document){
    const vids=$$('video[data-autoplay]',root);if(!('IntersectionObserver'in window))return;
    const ob=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting&&e.intersectionRatio>.65){$$('video[data-autoplay]').forEach(v=>{if(v!==e.target)v.pause();});e.target.play().catch(()=>{});}else e.target.pause();}),{threshold:[.2,.65,.9]});
    vids.forEach(v=>{if(!v.dataset.observed){v.dataset.observed='1';ob.observe(v);}});
  }

  function bindReelSound(root=document){
    $$('[data-reel-sound]',root).forEach(b=>{if(b.dataset.bound)return;b.dataset.bound='1';b.addEventListener('click',()=>{const reel=b.closest('.reel');const v=reel?.querySelector('video');if(!v)return;v.muted=!v.muted;b.classList.toggle('sound-on',!v.muted);showToast(v.muted?'Sound off':'Sound on');});});
  }
  function observeCards(root=document){
    if(!('IntersectionObserver' in window))return;
    const cards=$$('.post,.parent-card,.reel-teaser',root);
    const ob=new IntersectionObserver(entries=>entries.forEach(e=>{
      if(e.isIntersecting){e.target.classList.add('visible');ob.unobserve(e.target);}
    }),{threshold:.08});
    cards.forEach(c=>ob.observe(c));
  }

  function markActiveNav() {
    try {
      const path = window.location.pathname;
      $$('.bottom-nav a, .ig-bottom-nav a, .parent-nav a, .ig-desktop-nav-link').forEach(a => {
        const href = a.getAttribute('href');
        if (!href) return;
        const cleanHref = href.split('?')[0].split('#')[0];
        const cleanPath = path.split('?')[0].split('#')[0];
        if (cleanHref === cleanPath || (cleanHref !== '/' && cleanPath.startsWith(cleanHref))) {
          a.classList.add('active');
        } else {
          a.classList.remove('active');
        }
      });
    } catch (_) {}
  }

  function bindNotifFilters(root=document){
    $$('[data-notif-filter]', root).forEach(pill => {
      if (pill.dataset.bound) return;
      pill.dataset.bound = '1';
      pill.addEventListener('click', () => {
        const filter = pill.dataset.notifFilter;
        $$('[data-notif-filter]', root).forEach(p => {
          const isActive = (p === pill);
          p.classList.toggle('active', isActive);
          p.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        $$('[data-notif-item]', root).forEach(item => {
          const cat = item.dataset.notifCategory || 'all';
          const hasActor = !!item.dataset.actorId;
          let show = false;
          if (filter === 'all') show = true;
          else if (filter === 'comments' && cat === 'comments') show = true;
          else if (filter === 'follows' && cat === 'follows') show = true;
          else if (filter === 'people' && (hasActor || cat === 'people')) show = true;
          item.style.display = show ? 'flex' : 'none';
        });
        $$('[data-section-group]', root).forEach(sec => {
          const visibleItems = sec.querySelectorAll('[data-notif-item]:not([style*="display: none"])');
          sec.style.display = (visibleItems.length > 0) ? 'block' : 'none';
        });
      });
    });
  }

  function rebindAll(root=document){
    bindLike(root);
    bindFollow(root);
    bindShare(root);
    bindSave(root);
    bindReport(root);
    bindDouble(root);
    bindReelSound(root);
    bindNotifFilters(root);
    observeVideos(root);
    observeCards(root);
    markActiveNav();
    $$('img[data-hide-error]',root).forEach(img=>{
      const fallback=()=>{
        if(!img.dataset.fb){
          img.dataset.fb='1';
          img.src='/uploads/profile_pictures/download.webp';
        }
      };
      img.addEventListener('error',fallback);
    });
  }
  rebindAll();

  const storyRail=$('.stories');
  if(storyRail)storyRail.addEventListener('wheel',e=>{if(Math.abs(e.deltaY)>Math.abs(e.deltaX)){storyRail.scrollLeft+=e.deltaY;e.preventDefault();}},{passive:false});

  const reelsPage=$('.reels-page');
  if(reelsPage){
    let page=2,loading=false,done=false;
    reelsPage.addEventListener('scroll',async()=>{
      if(done||loading||reelsPage.scrollTop+reelsPage.clientHeight<reelsPage.scrollHeight-reelsPage.clientHeight*1.5)return;
      loading=true;
      try{
        const r=await fetch(`/api/reels/?page=${page}`,{cache:'no-store'});if(!r.ok){done=true;return;}
        const items=await r.json();if(!items.length){done=true;return;}
        items.forEach(x=>{
          const d=document.createElement('section');d.className='reel';d.dataset.doubleLike=x.post_id;
          d.innerHTML=`<video data-autoplay muted loop playsinline preload="metadata" src="/${escapeHtml(x.media_path)}"></video><div class="reel-overlay"></div><span class="heart-burst">♥</span><div class="reel-meta"><a href="/child/view-profile/${Number(x.child_id)}/" style="color:#fff;text-decoration:none"><b>${escapeHtml(x.full_name)}</b></a><p>${escapeHtml(x.caption)}</p><span class="safety-chip">${['Science','Math','Technology','Education','Nature','Books','Coding','General Knowledge'].includes(x.content_category)?'📚 '+escapeHtml(reelsPage.dataset.labelEducational||'Educational Reel'):escapeHtml(reelsPage.dataset.labelSafe||'Kids Safe')}</span></div><div class="reel-actions"><button data-like="${Number(x.post_id)}" aria-label="Like"><svg class="ln-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l7.8-7.5a5.5 5.5 0 0 0 1-8.9z"/></svg></button><a href="/post/${Number(x.post_id)}/" aria-label="Comments"><svg class="ln-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a8 8 0 0 1-8 8H6l-4 2 1.5-5A9 9 0 1 1 21 12z"/></svg></a><button data-share-post="${Number(x.post_id)}" aria-label="Share"><svg class="ln-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/></svg></button><button data-save-post="${Number(x.post_id)}" aria-label="Save"><svg class="ln-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z"/></svg></button><button data-reel-sound aria-label="Sound">🔊</button><button data-report-post="${Number(x.post_id)}" aria-label="Report">•••</button></div>`;
          reelsPage.appendChild(d);bindLike(d);bindShare(d);bindSave(d);bindReport(d);bindDouble(d);bindReelSound(d);observeVideos(d);
        });page++;
      }catch{done=true;}finally{loading=false;}
    });
  }

  function pollWhileVisible(poll,interval,onHidden){
    let timer=null,running=false,pending=false;
    const schedule=()=>{clearTimeout(timer);timer=document.hidden?null:setTimeout(run,interval);};
    const run=async()=>{
      if(document.hidden)return;
      if(running){pending=true;return;}
      running=true;
      try{await poll();}finally{running=false;if(pending&&!document.hidden){pending=false;run();}else schedule();}
    };
    document.addEventListener('visibilitychange',()=>{if(document.hidden){clearTimeout(timer);timer=null;pending=false;onHidden?.();}else run();});
    run();
  }

  if(document.body.dataset.role==='CHILD'){
    // End the usage segment while hidden; visibility resumes with a fresh segment.
    let childHeartbeatRequest=Promise.resolve();
    const childHeartbeat=active=>childHeartbeatRequest=childHeartbeatRequest.then(async()=>{try{const r=await fetch('/api/usage/heartbeat/',{method:'POST',headers:{'X-CSRFToken':csrf(),'Content-Type':'application/json'},body:JSON.stringify({active}),keepalive:!active});if(!r.ok||!active)return;const j=await r.json();if(j.quiet_hours&&j.redirect){location.href=j.redirect;return;}if(j.locked){location.href='/child/dashboard/';}}catch{}});
    pollWhileVisible(()=>childHeartbeat(true),30000,()=>childHeartbeat(false));
  }

  if(document.body.dataset.role==='PARENT') {
    const badge=$('[data-parent-alert-count]');
    const alertsLink=$('[data-parent-alerts]');
    let lastLatest=0;
    const pollParentAlerts=async()=>{
      try{
        const r=await fetch('/api/parent/notifications/unread/',{cache:'no-store'});
        if(!r.ok)return;
        const j=await r.json();
        const count=Number(j.count||0);
        if(badge){badge.textContent=String(count);badge.hidden=count===0;}
        if(alertsLink)alertsLink.classList.toggle('has-unread',count>0);
        const latest=Number(j.latest?.notification_id||0);
        if(latest && lastLatest && latest>lastLatest){
          alertsLink?.classList.add('alert-pulse');
          setTimeout(()=>alertsLink?.classList.remove('alert-pulse'),1200);
        }
        if(latest)lastLatest=Math.max(lastLatest,latest);
      }catch{}
    };
    if(badge||alertsLink)pollWhileVisible(pollParentAlerts,45000);
  }

  const upload=$('form[data-safe-upload]');
  if(upload){
    const status=$('#uploadStatus'),kind=upload.querySelector('[data-kind]'),music=upload.querySelector('[data-story-music]');
    const mediaInput=$('#media-input'),previewWrap=$('#mediaPreviewWrap'),imgPrev=$('#imagePreview'),vidPrev=$('#videoPreview'),audPrev=$('#audioPreview'),fileInfo=$('#fileInfoText'),dropIcon=$('#dropIconWrap'),dropMain=$('#dropMainText'),dropSub=$('#dropSubText');

    if(mediaInput){
      mediaInput.addEventListener('change',()=>{
        const file=mediaInput.files?.[0];
        if(!file)return;
        if(dropIcon)dropIcon.style.display='none';
        if(dropMain)dropMain.style.display='none';
        if(dropSub)dropSub.style.display='none';
        if(previewWrap)previewWrap.style.display='block';
        if(imgPrev)imgPrev.style.display='none';
        if(vidPrev)vidPrev.style.display='none';
        if(audPrev)audPrev.style.display='none';
        const url=URL.createObjectURL(file);
        if(file.type.startsWith('image/') && imgPrev){
          imgPrev.src=url;imgPrev.style.display='block';
        } else if(file.type.startsWith('video/') && vidPrev){
          vidPrev.src=url;vidPrev.style.display='block';
        } else if(file.type.startsWith('audio/') && audPrev){
          audPrev.src=url;audPrev.style.display='block';
        }
        if(fileInfo)fileInfo.textContent=`Selected: ${file.name} (${(file.size/1024/1024).toFixed(1)} MB)`;
      });
    }

    const sync=()=>{if(music)music.style.display=kind?.value==='story'?'block':'none';};kind?.addEventListener('change',sync);sync();
    upload.addEventListener('submit',async e=>{
      e.preventDefault();const btn=upload.querySelector('button[type=submit]');if(btn){btn.disabled=true;btn.style.opacity='0.7';}
      if(status){status.style.display='block';status.style.background='#fff7ed';status.style.color='#9a3412';status.style.border='1px solid #fed7aa';status.textContent='Running LittleNet safety checks...';}
      const data=new FormData(upload);const url=kind?.value==='story'?'/upload-story/':'/child/upload-post/';
      try{
        const r=await fetch(url,{method:'POST',headers:{'X-CSRFToken':csrf()},body:data});
        const j=await r.json();
        if(!r.ok){
          const reasonText = j.reason ? ('Blocked: ' + j.reason) : (j.error || 'Content could not be published.');
          if(status){
            status.style.display='block';
            status.style.background='#fef2f2';
            status.style.color='#b91c1c';
            status.style.border='1px solid #fecaca';
            status.textContent=reasonText;
          }
          if(btn){btn.disabled=false;btn.style.opacity='1';}
          return;
        }
        if(status){
          status.style.display='block';
          status.style.background='#f0fdf4';
          status.style.color='#15803d';
          status.style.border='1px solid #bbf7d0';
          status.textContent=j.status==='REVIEW'?'Sent to Parent Mode for review.':'Published safely!';
        }
        setTimeout(()=>{
          location.href=kind?.value==='reel'?'/reels/':(kind?.value==='story'?'/stories/':'/child/dashboard/');
        },600);
      }catch{
        if(status){
          status.style.display='block';
          status.style.background='#f0fdf4';
          status.style.color='#15803d';
          status.style.border='1px solid #bbf7d0';
          status.textContent='Upload completed. Opening your feed...';
        }
        setTimeout(()=>{location.href='/child/dashboard/';},1000);
      }finally{
        if(btn){btn.disabled=false;btn.style.opacity='1';}
      }
    });
  }

  const photo=$('form[data-profile-photo]');
  if(photo)photo.addEventListener('submit',async e=>{e.preventDefault();const data=new FormData(photo);try{const r=await fetch(photo.action,{method:'POST',headers:{'X-CSRFToken':csrf()},body:data});const j=await r.json();if(r.ok)location.reload();else showToast(j.error||'Profile photo was not allowed.');}catch{showToast('Photo upload failed.');}});

  // Auth & Login UI Handlers (CSP-compliant external execution)
  const tabKids = $('#tab-kids');
  const tabParent = $('#tab-parent');
  const formMode = $('#auth-mode-input');
  const subtitle = $('#mode-subtitle');
  const labelIdent = $('#label-identifier');
  const inputIdent = $('#auth-identifier');
  const inputPwd = $('#auth-password');
  const faceWrap = $('#face-login-wrap');
  const submitBtn = $('#auth-submit-btn');
  const authForm = $('#auth-form');

  function setAuthMode(mode) {
    if (mode === 'parent') {
      if (tabParent) {
        tabParent.classList.add('active', 'parent-active');
        tabParent.setAttribute('aria-selected', 'true');
      }
      if (tabKids) {
        tabKids.classList.remove('active', 'kid-active');
        tabKids.setAttribute('aria-selected', 'false');
      }
      if (formMode) formMode.value = 'parent';
      if (subtitle) subtitle.textContent = 'Parent supervision, screen-time & safety controls';
      if (labelIdent) labelIdent.textContent = 'Parent Email Address';
      if (inputIdent) inputIdent.placeholder = 'parent@example.com';
      if (faceWrap) faceWrap.style.display = 'none';
      if (submitBtn) {
        submitBtn.style.background = 'linear-gradient(135deg, #1E293B, #0F172A)';
        submitBtn.style.boxShadow = '0 8px 18px rgba(15, 23, 42, 0.25)';
        submitBtn.style.color = '#FFFFFF';
      }
      try { history.replaceState(null, '', '/login/?mode=parent'); } catch(e){}
    } else {
      if (tabKids) {
        tabKids.classList.add('active', 'kid-active');
        tabKids.setAttribute('aria-selected', 'true');
      }
      if (tabParent) {
        tabParent.classList.remove('active', 'parent-active');
        tabParent.setAttribute('aria-selected', 'false');
      }
      if (formMode) formMode.value = 'kids';
      if (subtitle) subtitle.textContent = 'A safe, AI-guided social world for children';
      if (labelIdent) labelIdent.textContent = 'Username or Child Email';
      if (inputIdent) inputIdent.placeholder = 'Enter username or child email';
      if (faceWrap) faceWrap.style.display = 'block';
      if (submitBtn) {
        submitBtn.style.background = 'linear-gradient(135deg, #0095F6, #1D4ED8)';
        submitBtn.style.boxShadow = '0 8px 20px rgba(0, 149, 246, 0.32)';
        submitBtn.style.color = '#FFFFFF';
      }
      try { history.replaceState(null, '', '/login/?mode=kids'); } catch(e){}
    }
  }

  if (tabKids) tabKids.addEventListener('click', (e) => { e.preventDefault(); setAuthMode('kids'); });
  if (tabParent) tabParent.addEventListener('click', (e) => { e.preventDefault(); setAuthMode('parent'); });

  const toggleBtn = $('#toggle-pwd-btn');
  if (toggleBtn && inputPwd) {
    const showIcon = toggleBtn.querySelector('.pwd-icon-show');
    const hideIcon = toggleBtn.querySelector('.pwd-icon-hide');
    toggleBtn.addEventListener('click', () => {
      const isPwd = inputPwd.type === 'password';
      inputPwd.type = isPwd ? 'text' : 'password';
      if (showIcon) showIcon.hidden = isPwd;
      if (hideIcon) hideIcon.hidden = !isPwd;
    });
  }

  if (authForm) {
    authForm.addEventListener('submit', () => {
      if (inputIdent) inputIdent.value = inputIdent.value.trim();
    });
  }

  $$('[data-fill-demo-id]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.fillDemoId;
      const pwd = btn.dataset.fillDemoPwd;
      const mode = btn.dataset.fillDemoMode;
      setAuthMode(mode);
      if (inputIdent) inputIdent.value = id;
      if (inputPwd) inputPwd.value = pwd;
      if (submitBtn) {
        submitBtn.classList.add('pulse');
        setTimeout(() => submitBtn.classList.remove('pulse'), 600);
      }
    });
  });

  if (formMode && formMode.value === 'parent') {
    setAuthMode('parent');
  }

  // Instant SPA Navigation Engine for native-like speed
  const pageCache = new Map();
  const progressBar = $('#ln-progress');

  function startProgress() {
    if (!progressBar) return;
    progressBar.style.width = '35%';
    progressBar.classList.add('loading');
    setTimeout(() => {
      if (progressBar.classList.contains('loading')) progressBar.style.width = '75%';
    }, 120);
  }

  function finishProgress() {
    if (!progressBar) return;
    progressBar.style.width = '100%';
    setTimeout(() => {
      progressBar.classList.remove('loading');
      setTimeout(() => { progressBar.style.width = '0%'; }, 200);
    }, 150);
  }

  async function fetchPage(url) {
    const cleanUrl = url.split('#')[0];
    if (pageCache.has(cleanUrl)) {
      const entry = pageCache.get(cleanUrl);
      if (Date.now() - entry.time < 120000) {
        return entry.html;
      }
    }
    const res = await fetch(cleanUrl, {
      headers: { 'X-Requested-With': 'LittleNetInstant' }
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const html = await res.text();
    pageCache.set(cleanUrl, { html, time: Date.now() });
    return html;
  }

  function prefetchUrl(url) {
    if (!url || !url.startsWith('/') || url.startsWith('/logout') || url.startsWith('/switch-mode') || url.startsWith('/language') || url.startsWith('/stories/') || url.startsWith('/uploads/') || url.startsWith('/static/')) return;
    const cleanUrl = url.split('#')[0];
    if (pageCache.has(cleanUrl)) return;
    fetchPage(cleanUrl).catch(() => {});
  }

  async function navigateTo(url, push = true) {
    if (!url || !url.startsWith('/')) return false;
    startProgress();
    try {
      const html = await fetchPage(url);
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const newPage = doc.querySelector('main.page');
      const curPage = document.querySelector('main.page');
      if (!newPage || !curPage) {
        window.location.href = url;
        return true;
      }
      if (doc.title) document.title = doc.title;
      if (push) history.pushState(null, '', url);

      curPage.innerHTML = newPage.innerHTML;
      curPage.className = newPage.className;
      curPage.classList.remove('page-swapping');
      void curPage.offsetWidth;
      curPage.classList.add('page-swapping');

      window.scrollTo(0, 0);
      rebindAll();
      finishProgress();
      return true;
    } catch (err) {
      finishProgress();
      window.location.href = url;
      return false;
    }
  }

  // Intercept internal navigation clicks
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const link = e.target.closest('a');
    if (!link) return;
    const href = link.getAttribute('href');
    if (!href || !href.startsWith('/') || href.startsWith('/#')) return;
    if (link.hasAttribute('download') || link.getAttribute('target') === '_blank' || link.hasAttribute('data-no-instant')) return;
    if (href.startsWith('/logout') || href.startsWith('/switch-mode') || href.startsWith('/language') || href.startsWith('/stories/') || href.startsWith('/child/upload-post') || href.startsWith('/uploads/')) {
      return;
    }
    e.preventDefault();
    // Instant active tab feedback
    const navItems = link.closest('.bottom-nav, .ig-bottom-nav, .parent-nav');
    if (navItems) {
      navItems.querySelectorAll('a').forEach(a => a.classList.remove('active'));
      link.classList.add('active');
    }
    navigateTo(href, true);
  });

  // Pre-fetch on hover or touch
  document.addEventListener('pointerenter', (e) => {
    const link = e.target.closest?.('a');
    if (link) prefetchUrl(link.getAttribute('href'));
  }, true);

  document.addEventListener('touchstart', (e) => {
    const link = e.target.closest?.('a');
    if (link) prefetchUrl(link.getAttribute('href'));
  }, { passive: true });

  // Handle browser back and forward navigation
  window.addEventListener('popstate', () => {
    navigateTo(location.pathname + location.search, false);
  });

  window.addEventListener('load', () => {
    if('serviceWorker' in navigator){
      navigator.serviceWorker.register('/sw.js').catch(()=>{});
    }
  });
})();
