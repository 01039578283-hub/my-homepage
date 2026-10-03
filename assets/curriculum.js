(() => {
  'use strict';
  const directory = document.querySelector('[data-cu-directory]');
  if (!directory) return;
  const search = directory.querySelector('[data-cu-search]');
  const stage = directory.querySelector('[data-cu-stage]');
  const grade = directory.querySelector('[data-cu-grade]');
  const subject = directory.querySelector('[data-cu-subject]');
  const cards = [...directory.querySelectorAll('[data-cu-card]')];
  const status = directory.querySelector('[data-cu-count]');
  const empty = directory.querySelector('[data-cu-empty]');
  const update = () => {
    const term = search.value.trim().toLocaleLowerCase('ko-KR');
    let visible = 0;
    cards.forEach(card => {
      const matched = (!term || card.textContent.toLocaleLowerCase('ko-KR').includes(term)) &&
        (!stage.value || card.dataset.stage === stage.value) &&
        (!grade.value || card.dataset.grade === grade.value) &&
        (!subject.value || card.dataset.subject === subject.value);
      card.hidden = !matched;
      if (matched) visible++;
    });
    status.textContent = `66개 학습 안내 중 ${visible}개를 볼 수 있습니다.`;
    empty.hidden = visible > 0;
  };
  const updateGrades = () => {
    const selected = grade.value;
    const choices = [...new Set(cards.filter(card => !stage.value || card.dataset.stage === stage.value).map(card => card.dataset.grade))];
    grade.replaceChildren(new Option('모든 학년', ''));
    choices.forEach(name => grade.add(new Option(name, name)));
    grade.value = choices.includes(selected) ? selected : '';
    update();
  };
  search.addEventListener('input', update);
  stage.addEventListener('change', updateGrades);
  grade.addEventListener('change', update);
  subject.addEventListener('change', update);
  directory.querySelector('[data-cu-reset]').addEventListener('click', () => {
    search.value = ''; stage.value = ''; grade.value = ''; subject.value = '';
    updateGrades(); search.focus();
  });
  directory.querySelector('[data-cu-filters]').hidden = false;
  update();
})();
