/* Source-backed subject/grade matching; no requests or hidden directory fetch. */
(() => {
  'use strict';
  const input = document.querySelector('[data-branch-search-input]');
  if (!input) return;
  const subject = document.querySelector('#branch-course-subject');
  const grade = document.querySelector('#branch-course-grade');
  const reset = document.querySelector('[data-branch-search-reset]');
  const cards = [...document.querySelectorAll('[data-branch-card]')];
  const status = document.querySelector('[data-branch-search-status]');
  const count = document.querySelector('[data-branch-count]');
  const empty = document.querySelector('[data-branch-empty]');
  const normalize = value => String(value || '').normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s+/g, '');
  const courseMatch = pairs => pairs.split(' ').filter(Boolean).some(pair => {
    const [s,g] = pair.split(':');
    return (!subject.value || subject.value === s) && (!grade.value || grade.value === g);
  });
  const apply = () => {
    const words = input.value.trim().split(/\s+/).map(normalize).filter(Boolean);
    const filtered = Boolean(subject.value || grade.value);
    let visible = 0, pending = 0;
    cards.forEach(card => {
      const textMatch = words.every(word => normalize(card.dataset.search).includes(word));
      const confirmed = !filtered || courseMatch(card.dataset.coursePairs || '');
      const needsCheck = filtered && !confirmed && courseMatch(card.dataset.pendingPairs || '');
      card.hidden = !(textMatch && (confirmed || needsCheck));
      let notice = card.querySelector('.wn-pending-course');
      if (needsCheck && !notice) {
        notice = document.createElement('span'); notice.className = 'wn-pending-course';
        notice.textContent = '선택한 학년·과목은 현재 개설 여부 확인이 필요합니다.';card.append(notice);
      }
      if (notice) notice.hidden = !needsCheck;
      if (!card.hidden) { visible++; if (needsCheck) pending++; }
    });
    const label = `${visible}개 센터${pending ? ` · 개설 확인 필요 ${pending}개 포함` : ''}`;
    if (count) count.textContent = label;
    if (status) status.textContent = (words.length || filtered ? '검색 결과 ' : '전체 ') + label;
    if (empty) empty.hidden = visible !== 0;
    if (reset) reset.disabled = !(words.length || filtered);
  };
  input.addEventListener('input', apply);input.addEventListener('search', apply);
  subject.addEventListener('change', apply);grade.addEventListener('change', apply);
  reset.addEventListener('click', () => { input.value='';subject.value='';grade.value='';apply();input.focus(); });
  apply();
})();
