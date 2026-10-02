(() => {
  // LittleNet pages include a number of page-specific camera, chat, quiz and
  // safety scripts. Full document navigation guarantees those scripts are
  // initialized every time and avoids stale DOM/event state from partial swaps.
  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest && event.target.closest('a');
    if (!link) return;
    const href = link.getAttribute('href') || '';
    if (!href.startsWith('/') || href.startsWith('/#')) return;
    if (link.hasAttribute('download') || link.getAttribute('target') === '_blank') return;
    // Do not prevent the browser's default action; only stop LittleNet's older
    // bubble-phase SPA click handler from replacing <main> without re-running
    // page scripts.
    event.stopPropagation();
  }, true);
})();
