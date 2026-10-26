/* Native details/anchors remain usable without JavaScript. No network calls. */
(() => {
  'use strict';
  const header = document.querySelector('[data-navigation-upgrade]');
  if (!header) return;
  const groups = [...header.querySelectorAll('.wn-group')];
  header.addEventListener('click', event => {
    const summary = event.target.closest('summary');
    if (summary) groups.forEach(group => { if (group !== summary.parentElement) group.open = false; });
    if (event.target.closest('.wn-panel a')) groups.forEach(group => { group.open = false; });
  });
  document.addEventListener('click', event => {
    if (!header.contains(event.target)) groups.forEach(group => { group.open = false; });
  });
  header.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const open = groups.find(group => group.open);
    if (open) { open.open = false; open.querySelector('summary').focus(); }
  });
})();
