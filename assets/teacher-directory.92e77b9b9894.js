(() => {
  'use strict';
  const form = document.querySelector('[data-teacher-filters]');
  if (!form) return;
  const region = form.querySelector('#teacher-region');
  const search = form.querySelector('#teacher-search');
  const cards = [...document.querySelectorAll('[data-branch-card]')];
  const status = document.querySelector('[data-result-count]');
  const empty = document.querySelector('[data-empty]');
  const normalize = text => text.normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s+/g, '');
  const apply = () => {
    const words = search.value.trim().split(/\s+/).map(normalize).filter(Boolean);
    let branches = 0, introductions = 0;
    for (const card of cards) {
      const matchRegion = !region.value || (region.value === 'unconfirmed' ? !card.dataset.region : card.dataset.region === region.value);
      const haystack = normalize(card.dataset.search);
      card.hidden = !(matchRegion && words.every(word => haystack.includes(word)));
      if (!card.hidden) {
        branches++;
        introductions += Number(card.querySelector('.td-card-count').textContent.match(/\d+/)[0]);
      }
    }
    status.textContent = `지점 ${branches}개 · 선생님 소개 ${introductions}개`;
    empty.hidden = branches !== 0;
  };
  form.addEventListener('submit', event => event.preventDefault());
  region.addEventListener('change', apply);
  search.addEventListener('input', apply);
  form.addEventListener('reset', () => requestAnimationFrame(apply));
  apply();
})();
