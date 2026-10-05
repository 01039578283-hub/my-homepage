/* Progressive enhancement: all content and YouTube links work without JavaScript. */
(() => {
  'use strict';
  if (!document.body.classList.contains('wawa-upgrade')) return;
  const allowedIds = new Set(['avpJfW7eIV0', 'f_skFu40U04', 'UIXUaBZdNXU']);
  document.querySelectorAll('.wu-video-player[data-video]').forEach((player) => {
    const launch = player.querySelector('.wu-video-launch');
    const id = player.dataset.video;
    if (!launch || !allowedIds.has(id)) return;
    const poster = launch.cloneNode(true);
    let actions;
    function stop() {
      const restored = poster.cloneNode(true);
      player.replaceChildren(restored);
      actions?.remove();
      restored.addEventListener('click', start);
      restored.focus({ preventScroll:true });
    }
    function start(event) {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button > 0) return;
      event.preventDefault();
      if (player.querySelector('iframe')) return;
      const frame = document.createElement('iframe');
      frame.src = `https://www.youtube-nocookie.com/embed/${id}?playsinline=1&rel=0`;
      frame.title = player.dataset.videoTitle;
      frame.allow = 'encrypted-media; picture-in-picture; fullscreen';
      frame.allowFullscreen = true;
      frame.referrerPolicy = 'strict-origin-when-cross-origin';
      frame.tabIndex = 0;
      const close = document.createElement('button');
      close.type = 'button';
      close.textContent = '영상 닫기';
      close.setAttribute('aria-label', `${frame.title} 닫기`);
      close.addEventListener('click', stop);
      const external = document.createElement('a');
      external.href = poster.href;
      external.target = '_blank';
      external.rel = 'noopener';
      external.textContent = 'YouTube 열기';
      actions = document.createElement('div');
      actions.className = 'wu-video-actions';
      actions.append(external,close);
      player.replaceChildren(frame);
      player.after(actions);
      frame.focus({ preventScroll:true });
    }
    launch.addEventListener('click', start);
  });
  // Preserve the existing fees and make the legacy home FAQ keyboard/AT friendly.
  document.querySelectorAll('.faq-item').forEach((item, index) => {
    const question = item.querySelector('.faq-question');
    const answer = item.querySelector('.faq-answer');
    if (!question || !answer) return;
    question.id = `home-question-${index + 1}`;
    question.setAttribute('aria-label',question.textContent.trim());
    answer.id = `home-answer-${index + 1}`;
    answer.setAttribute('role','region');
    answer.setAttribute('aria-labelledby',question.id);
    question.setAttribute('aria-controls',answer.id);
    function setOpen(open) {
      item.classList.toggle('active',open);
      question.setAttribute('aria-expanded',String(open));
      answer.hidden = !open;
    }
    setOpen(item.classList.contains('active'));
    question.addEventListener('click',() => setOpen(question.getAttribute('aria-expanded') !== 'true'));
  });
})();
