/* Worksheet entries stay in the current document; saving creates a local text file. */
(() => {
  'use strict';
  document.querySelectorAll('[data-overlap-worksheet]').forEach(form => {
    const status = form.querySelector('[data-work-status]');
    const save = form.querySelector('[data-work-save]');
    if (!save || !status) return;
    form.addEventListener('submit', event => event.preventDefault());
    form.addEventListener('reset', () => { status.textContent = '작성 내용을 비웠습니다.'; });
    save.addEventListener('click', () => {
      const title = form.dataset.workTitle || '상담 전 학습 점검표';
      const canonical = document.querySelector('link[rel="canonical"]')?.href || location.href.split('#')[0];
      const lines = [title, canonical, ''];
      form.querySelectorAll('textarea').forEach(field => {
        lines.push(`[${field.dataset.workLabel}]`, field.value.trim() || '(아직 작성하지 않음)', '');
      });
      const file = new Blob(['\ufeff', lines.join('\r\n')], {type: 'text/plain;charset=utf-8'});
      const url = URL.createObjectURL(file);
      const link = document.createElement('a');
      link.href = url;
      link.download = title.replace(/[\\/:*?"<>|]/g, '-') + '.txt';
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = '점검표의 텍스트 파일 저장을 요청했습니다.';
    });
  });
})();
