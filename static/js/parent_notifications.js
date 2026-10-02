(() => {
  const button = document.querySelector('[data-mark-parent-alerts-read]');
  if (!button) return;
  button.addEventListener('click', async () => {
    const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
    button.disabled = true;
    try {
      const response = await fetch('/parent/notifications/read/', {
        method: 'POST',
        headers: { 'X-CSRFToken': token }
      });
      if (!response.ok) throw new Error('request_failed');
      document.querySelectorAll('.notification-unread').forEach((el) => el.classList.remove('notification-unread'));
      const badge = document.querySelector('[data-parent-alert-count]');
      if (badge) { badge.textContent = '0'; badge.hidden = true; }
      button.textContent = 'All read';
    } catch (_) {
      button.textContent = 'Try again';
      button.disabled = false;
    }
  });
})();
