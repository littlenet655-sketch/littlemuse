(()=>{const box=document.getElementById('messages');if(!box)return;const peer=box.dataset.peer,me=Number(box.dataset.me);let sig='';
 function safePath(p){return p?'/'+String(p).replace(/^\/+/, ''):''}
 function render(rows){const near=box.scrollHeight-box.scrollTop-box.clientHeight<100;box.replaceChildren();for(const m of rows){const b=document.createElement('div');b.className='bubble '+(Number(m.sender_child_id)===me?'mine':'');b.dataset.messageId=m.child_message_id;let el;if(m.message_type==='TEXT'){el=document.createElement('span');el.textContent=m.message_text||''}else if(m.message_type==='IMAGE'){el=document.createElement('img');el.className='chat-media';el.loading='lazy';el.src=safePath(m.media_path)}else if(m.message_type==='VIDEO'){el=document.createElement('video');el.className='chat-media';el.controls=true;el.playsInline=true;el.preload='metadata';el.src=safePath(m.media_path)}else if(m.message_type==='VOICE'){el=document.createElement('audio');el.controls=true;el.preload='metadata';el.src=safePath(m.media_path)}else if(m.message_type==='FILE'){el=document.createElement('a');el.className='chat-file';el.href=safePath(m.media_path);el.target='_blank';el.textContent='Open attachment'}else if(m.message_type==='SHARED_POST'){el=document.createElement('a');el.className='shared-post';el.href=`/post/${m.shared_post_id}/`;el.textContent='▣ Shared safe post'}if(el)b.appendChild(el);const st=document.createElement('small');st.className='message-status';if(m.moderation_status==='REVIEW')st.textContent='Waiting for parent review';else if(Number(m.sender_child_id)===me)st.textContent=m.is_seen?'Seen':m.delivered_at?'Delivered':'Sent';if(st.textContent)b.appendChild(st);box.appendChild(b)}if(near||!sig)box.scrollTop=box.scrollHeight}
 async function poll(){try{const r=await fetch(`/api/chat/${peer}/messages/`,{cache:'no-store'});if(!r.ok)return;const rows=await r.json();const ns=rows.map(x=>[x.child_message_id,x.moderation_status,x.is_seen,x.delivered_at].join(':')).join('|');if(ns!==sig){sig=ns;render(rows)}}catch{}}
 box.scrollTop=box.scrollHeight;poll();setInterval(poll,2500);
})();
;(()=>{
  const form=document.querySelector('.ig-chat-main-form');
  if(!form)return;
  const token=document.querySelector('meta[name="csrf-token"]')?.content||form.querySelector('input[name="csrf_token"]')?.value||'';
  const input=form.querySelector('.ig-chat-text-input');
  form.addEventListener('submit',async e=>{
    e.preventDefault();
    const text=(input?.value||'').trim();
    if(!text)return;
    const btn=form.querySelector('.ig-chat-send-btn');
    if(btn)btn.disabled=true;
    const toast=window.lnToast||((m)=>console.warn(m));
    try{
      const r=await fetch(form.action,{method:'POST',headers:{'X-CSRFToken':token},body:new FormData(form)});
      let j={};try{j=await r.json();}catch{}
      if(!r.ok||j.blocked){
        toast(j.error||j.reason||"This message can't be sent for safety.");
        return;
      }
      if(input)input.value='';
      // The next poll (every 2.5s) will render the sent message.
    }catch{toast('Message could not be sent. Check your connection and try again.')}
    finally{if(btn)btn.disabled=false}
  });
})();
;(()=>{
  const form=document.querySelector('form[data-media-form]');
  if(!form)return;
  const cameraBtn=document.querySelector('[data-chat-camera]');
  const fileInput=form.querySelector('[data-chat-file]');
  if(cameraBtn&&fileInput){
    cameraBtn.addEventListener('click',()=>fileInput.click());
    fileInput.addEventListener('change',()=>{if(fileInput.files&&fileInput.files.length)form.requestSubmit();});
  }
  const token=document.querySelector('meta[name="csrf-token"]')?.content||'';
  form.addEventListener('submit',async e=>{
    e.preventDefault();
    const btn=form.querySelector('button');
    if(btn)btn.disabled=true;
    try{
      const r=await fetch(form.action,{method:'POST',headers:{'X-CSRFToken':token},body:new FormData(form)});
      const j=await r.json();
      const toast=window.lnToast||((m)=>console.warn(m));
      if(!r.ok){toast(j.reason||j.error||'Attachment blocked or failed.');return}
      form.reset();
    }catch{(window.lnToast||console.warn)('Attachment could not be sent.')}
    finally{if(btn)btn.disabled=false}
  });
})();
