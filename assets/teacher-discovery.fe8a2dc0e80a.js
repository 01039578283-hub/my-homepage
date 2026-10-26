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
    let branches=0, introductions=0, unconfirmed=0;
    for (const card of cards) {
      const matchRegion = !region.value || (region.value === 'unconfirmed' ? !card.dataset.region : card.dataset.region === region.value);
      const haystack = normalize(card.dataset.search);
      card.hidden = !(matchRegion && words.every(word => haystack.includes(word)));
      if (!card.hidden) {
        branches++; introductions += Number(card.querySelector('.td-card-count').textContent.match(/\d+/)[0]);
        if (!card.dataset.region) unconfirmed++;
      }
    }
    status.textContent = `소개 자료 ${branches}개 지점 · 선생님 소개 ${introductions}개${unconfirmed ? ` · 지점 정보 확인 필요 ${unconfirmed}개 포함` : ''}`;
    empty.hidden = branches !== 0;
  };
  form.addEventListener('submit', event => event.preventDefault());
  region.addEventListener('change', apply);search.addEventListener('input', apply);
  form.addEventListener('reset', () => requestAnimationFrame(apply));apply();
})();
