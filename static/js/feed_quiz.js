/**
 * LittleNet brain-break NUDGE (non-blocking).
 *
 * PostgreSQL owns the view counter and the quiz-due signal. The browser only
 * reports concrete post/reel IDs after they become substantially visible, and
 * renders a DISMISSIBLE prompt card when a quiz is due. Content is never
 * blocked: a child who ignores the card keeps full access (defect: the
 * periodic latch is a nudge, not a session lock).
 */

const FeedQuiz = (() => {
  // Kept as a UI/source-contract fallback only. The authoritative interval is
  // returned by the server and is never counted in browser memory.
  const QUIZ_INTERVAL = 4;
  let currentQuizId = null;
  let quizAnswered = false;
  let nudgeDismissed = false; // per page view: a dismissed nudge never re-nags
  let nudgeOpen = false;

  function _csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  async function _json(url, options = {}) {
    const res = await fetch(url, { credentials: 'same-origin', ...options });
    let data = {};
    try { data = await res.json(); } catch (_) { data = {}; }
    if (!res.ok) {
      const err = new Error(data.error || `request failed (${res.status})`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function _postId(target) {
    const raw = target?.dataset?.postCard || target?.dataset?.doubleLike || target?.dataset?.postId || '';
    const id = Number.parseInt(String(raw), 10);
    return Number.isFinite(id) && id > 0 ? id : null;
  }

  /** Called whenever a real feed/reel item becomes substantially visible. */
  async function onPostViewed(target) {
    const postId = typeof target === 'number' ? target : _postId(target);
    if (!postId) return;

    try {
      const state = await _json('/quiz/api/feed-view/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
        body: JSON.stringify({ post_id: postId }),
      });
      // The server is authoritative. It may report a smaller parent-configured
      // interval, but it can never be larger than the LittleNet safety default.
      const interval = Number(state.interval || QUIZ_INTERVAL);
      void interval;
      // Nudge, never lock: the view is always counted; the card is optional.
      if (state.required) _showNudgeCard();
    } catch (_) {
      // Telemetry is non-blocking: a failed view report never locks scrolling.
    }
  }

  async function _syncRequiredState() {
    // A server-rendered prompt card between reels takes precedence on load.
    if (document.getElementById('quiz-prompt-card')) return;
    try {
      const state = await _json('/quiz/api/feed-quiz/status/');
      if (state.required) _showNudgeCard();
    } catch (_) {
      // Fail open: status trouble never blocks the child.
    }
  }

  /** Dismissible bottom-sheet shell (not modal, never locks scroll). */
  function _nudgeShell() {
    document.querySelectorAll('.feed-quiz-nudge').forEach(el => el.remove());
    const shell = document.createElement('div');
    shell.className = 'feed-quiz-nudge';
    shell.setAttribute('role', 'dialog');
    shell.setAttribute('aria-label', 'Brain break quiz prompt');
    shell.style.cssText = 'position:fixed;left:12px;right:12px;bottom:76px;z-index:99990;display:flex;justify-content:center;pointer-events:none;';
    const card = document.createElement('div');
    card.className = 'feed-quiz-card fq-visible';
    card.style.cssText = 'pointer-events:auto;width:min(520px,100%);background:#fff;border-radius:24px;padding:22px;box-shadow:0 28px 70px rgba(0,0,0,.28);position:relative;';
    shell.appendChild(card);
    document.body.appendChild(shell);
    nudgeOpen = true;
    return card;
  }

  function _closeNudge() {
    document.querySelectorAll('.feed-quiz-nudge').forEach(el => el.remove());
    nudgeOpen = false;
  }

  function _dismissNudge() {
    nudgeDismissed = true;
    _closeNudge();
  }

  function _xButton(onClick) {
    const x = document.createElement('button');
    x.type = 'button';
    x.setAttribute('aria-label', 'Dismiss quiz prompt');
    x.textContent = '✕';
    x.style.cssText = 'position:absolute;top:10px;right:12px;border:0;background:none;font-size:16px;color:#94A3B8;cursor:pointer;padding:6px;';
    x.addEventListener('click', onClick);
    return x;
  }

  /** The non-blocking prompt: take the quiz, or dismiss and keep scrolling. */
  function _showNudgeCard() {
    if (nudgeDismissed || nudgeOpen) return;
    const card = _nudgeShell();
    card.appendChild(_xButton(_dismissNudge));
    card.insertAdjacentHTML('beforeend', `
      <div class="fq-header"><span class="fq-badge">🧠 Brain Break</span></div>
      <p class="fq-question">Time for a quick brain break!</p>
      <p class="fq-sub">A short quiz is ready for you. Your scrolling keeps working — no rush.</p>
      <div class="fq-options">
        <button class="fq-option fq-primary" id="fq-take-quiz" type="button" style="width:100%;">Take the quiz</button>
        <button class="fq-option" id="fq-not-now" type="button" style="width:100%;">Not now</button>
      </div>
    `);
    card.querySelector('#fq-take-quiz').addEventListener('click', () => { void _loadQuizIntoNudge(card); });
    card.querySelector('#fq-not-now').addEventListener('click', _dismissNudge);
  }

  async function _loadQuizIntoNudge(card) {
    card.innerHTML = '<p class="fq-question">Loading your quiz…</p>';
    card.appendChild(_xButton(_dismissNudge));
    try {
      const data = await _json('/quiz/api/feed-quiz/');
      if (!data.available || !data.required) throw new Error('no quiz available');
      currentQuizId = data.quiz_id;
      quizAnswered = false;
      _renderQuizForm(data, card);
    } catch (_) {
      // Fail open: quiz-service trouble never blocks the child.
      _dismissNudge();
    }
  }

  function _renderQuizForm(data, card) {
    const emojis = { 'Science':'🔬', 'Math':'➕', 'Riddle':'🧩', 'General Knowledge':'🌍',
      'India Special':'🇮🇳', 'Fun Fact':'🤩', 'Technology':'💻', 'Coding':'👨‍💻',
      'Internet Safety':'🔐', 'Environment':'🌿', 'Space':'🚀', 'Health':'❤️',
      'Emoji Quiz':'😊', 'Digital Safety':'🛡️', 'Kindness':'💛', 'Digital Etiquette':'🤝',
      'Digital Literacy':'📰', 'Cyber Safety':'🔒' };
    const icon = emojis[data.category] || '❓';

    card.innerHTML = `
      <div class="fq-header">
        <span class="fq-badge">${icon} Brain Break</span>
        <span class="fq-xp-badge">+10 XP ⭐</span>
      </div>
      <div class="fq-category">${_escape(data.category)}</div>
      <p class="fq-question">${_escape(data.question)}</p>
      <div class="fq-options" id="fq-options-${data.quiz_id}">
        ${data.options.map(opt => `
          <button class="fq-option" data-answer="${_escape(opt)}" type="button">
            <span class="fq-opt-dot"></span><span>${_escape(opt)}</span>
          </button>
        `).join('')}
      </div>
      <div class="fq-feedback" id="fq-feedback-${data.quiz_id}" hidden></div>
      <div style="margin-top:14px;font-size:12px;font-weight:700;opacity:.72;text-align:center;">Take it when you like — nothing is blocked.</div>
    `;
    card.appendChild(_xButton(_dismissNudge));

    card.querySelectorAll('.fq-option[data-answer]').forEach(btn => {
      btn.addEventListener('click', () => _submitAnswer(btn.dataset.answer, data, card));
    });
  }

  async function _submitAnswer(answer, data, card) {
    if (quizAnswered) return;
    if (Number(data.quiz_id) !== Number(currentQuizId)) return;
    quizAnswered = true;
    card.querySelectorAll('.fq-option[data-answer]').forEach(b => { b.disabled = true; b.classList.add('fq-disabled'); });
    card.querySelectorAll('.fq-option[data-answer]').forEach(b => { if (b.dataset.answer === answer) b.classList.add('fq-selected'); });

    try {
      const result = await _json('/quiz/api/feed-quiz/answer/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
        body: JSON.stringify({ quiz_id: data.quiz_id, answer }),
      });

      card.querySelectorAll('.fq-option[data-answer]').forEach(b => {
        if (b.dataset.answer === result.correct_answer) b.classList.add('fq-correct');
        else if (b.dataset.answer === answer && !result.correct) b.classList.add('fq-wrong');
      });

      const fb = card.querySelector(`#fq-feedback-${data.quiz_id}`);
      fb.hidden = false;
      if (result.correct) {
        fb.className = 'fq-feedback fq-feedback-correct';
        fb.innerHTML = `🎉 <b>Correct!</b> +${result.xp || 10} XP earned!${result.bonus_xp ? ` ⚡ Streak bonus: +${result.bonus_xp} XP!` : ''}${result.explanation ? `<div class="fq-explanation">💡 ${_escape(result.explanation)}</div>` : ''}`;
        _confetti(card);
      } else {
        fb.className = 'fq-feedback fq-feedback-wrong';
        fb.innerHTML = `💡 Good try! The correct answer was <b>${_escape(result.correct_answer)}</b>${result.explanation ? `<div class="fq-explanation">📖 ${_escape(result.explanation)}</div>` : ''}`;
      }

      // Any accepted answer satisfies the nudge; the server has already
      // cleared the quiz-due signal. The card goes away on its own.
      setTimeout(() => { currentQuizId = null; _closeNudge(); }, result.explanation ? 2800 : 1800);
    } catch (e) {
      quizAnswered = false;
      card.querySelectorAll('.fq-option[data-answer]').forEach(b => { b.disabled = false; b.classList.remove('fq-disabled'); });
      const fb = card.querySelector(`#fq-feedback-${data.quiz_id}`);
      fb.hidden = false;
      fb.className = 'fq-feedback fq-feedback-wrong';
      fb.textContent = 'Could not submit yet. Please try again.';
    }
  }

  function _confetti(container) {
    for (let i = 0; i < 22; i++) {
      const dot = document.createElement('span');
      dot.className = 'fq-confetti-dot';
      dot.style.cssText = `left:${Math.random()*100}%;width:${6+Math.random()*8}px;height:${6+Math.random()*8}px;animation-delay:${Math.random()*.35}s;animation-duration:${.8+Math.random()*.6}s;`;
      container.appendChild(dot);setTimeout(() => dot.remove(),1800);
    }
  }

  function _escape(str) {
    return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function init() {
    if (!('IntersectionObserver' in window)) return;
    const selector = '.ig-post, .reel:not(.feed-quiz-reel)';
    const initialTargets = [...document.querySelectorAll(selector)];
    if (!initialTargets.length) return;

    // Catch a quiz-due signal raised in another tab before any new view lands.
    _syncRequiredState();

    const seen = new WeakSet();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting && e.intersectionRatio >= .65 && !seen.has(e.target)) {
          seen.add(e.target);
          onPostViewed(e.target);
        }
      });
    }, { threshold: [0.65] });
    initialTargets.forEach(el => observer.observe(el));

    const mo = new MutationObserver(mutations => {
      mutations.forEach(m => m.addedNodes.forEach(n => {
        if (n.nodeType === 1) {
          if (n.matches?.(selector)) observer.observe(n);
          n.querySelectorAll?.(selector).forEach(el => observer.observe(el));
        }
      }));
    });
    const feed = document.querySelector('.ig-feed, .feed, .reels-page, #reels-container, .page');
    if (feed) mo.observe(feed, { childList:true, subtree:true });
  }

  return { init, onPostViewed };
})();

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', FeedQuiz.init);
else FeedQuiz.init();
