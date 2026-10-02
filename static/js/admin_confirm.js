/* LittleNet admin: CSP-safe delegated form confirmation.
 * Any form with a data-confirm attribute shows a native confirm() dialog
 * with the attribute's message and cancels submission when declined.
 * No inline event handlers are used, keeping strict Content-Security-Policy
 * (script-src 'self') intact.
 */
(function () {
  'use strict';
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || !form.hasAttribute || !form.hasAttribute('data-confirm')) {
      return;
    }
    var message = form.getAttribute('data-confirm') || 'Are you sure?';
    if (!window.confirm(message)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);
})();
