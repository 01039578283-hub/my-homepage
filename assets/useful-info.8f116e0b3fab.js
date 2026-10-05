(() => {
  'use strict';
  const directory = document.querySelector('[data-ui-directory]');
  if (directory) {
    const search = directory.querySelector('[data-ui-search]');
    const category = directory.querySelector('[data-ui-category]');
    const cards = [...directory.querySelectorAll('[data-ui-card]')];
    const count = directory.querySelector('[data-ui-count]');
    const empty = directory.querySelector('[data-ui-empty]');
    const update = () => {
      const query = search.value.trim().toLocaleLowerCase('ko-KR');
      let visible = 0;
      cards.forEach(card => {
        const matched = (!query || card.textContent.toLocaleLowerCase('ko-KR').includes(query)) && (!category.value || card.dataset.category === category.value);
        card.hidden = !matched;
        if (matched) visible++;
      });
      count.textContent = `${cards.length}개 중 ${visible}개의 글을 볼 수 있습니다.`;
      empty.hidden = visible > 0;
    };
    directory.querySelector('[data-ui-filters]').hidden = false;
    search.addEventListener('input', update);
    category.addEventListener('change', update);
    directory.querySelectorAll('[data-ui-reset]').forEach(button => button.addEventListener('click', () => {search.value = ''; category.value = ''; update(); search.focus();}));
    update();
  }
  const finder = document.querySelector('[data-ui-places]');
  if (!finder) return;
  const region = finder.querySelector('[data-ui-region]');
  const query = finder.querySelector('[data-ui-place-search]');
  const branch = finder.querySelector('[data-ui-branch]');
  const result = finder.querySelector('[data-ui-place-result]');
  const status = finder.querySelector('[data-ui-place-status]');
  let places = [];
  const hideResult = () => {result.replaceChildren(); result.hidden = true;};
  const list = () => {
    const term = query.value.trim().toLocaleLowerCase('ko-KR');
    const filtered = places.filter(p => (!region.value || p.region === region.value) && (!term || `${p.name} ${p.address} ${p.localities.map(n => n.name).join(' ')}`.toLocaleLowerCase('ko-KR').includes(term)));
    branch.replaceChildren(new Option(filtered.length ? '지점을 선택하세요' : '조건에 맞는 지점이 없습니다', ''));
    filtered.forEach(p => branch.add(new Option(`${p.name} · ${p.district}`, p.url)));
    hideResult();
    status.textContent = `${filtered.length}개 지점의 안내를 선택할 수 있습니다.`;
  };
  const anchor = (label, url, primary = false) => {
    const a = document.createElement('a'); a.textContent = label; a.href = url;
    if (primary) a.className = 'ui-primary';
    return a;
  };
  fetch('/assets/useful-places.json?v=20261002', {credentials:'omit'}).then(response => {
    if (!response.ok) throw new Error('directory unavailable');
    return response.json();
  }).then(data => {
    places = data;
    [...new Set(places.map(p => p.region))].sort((a,b) => a.localeCompare(b,'ko')).forEach(name => region.add(new Option(name,name)));
    finder.querySelector('[data-ui-place-controls]').hidden = false;
    region.addEventListener('change', list); query.addEventListener('input', list);
    branch.addEventListener('change', () => {
      hideResult(); const place = places.find(p => p.url === branch.value); if (!place) return;
      const address = document.createElement('p'); address.textContent = place.address;
      const links = document.createElement('div'); links.className = 'ui-buttons';
      links.append(anchor(`${place.name} 지점 안내`,place.url,true));
      place.localities.forEach(n => links.append(anchor(`${n.name} 동네 학습 안내`,n.url)));
      result.append(address,links); result.hidden = false;
      status.textContent = `${place.name}의 지점·동네 안내 버튼을 열었습니다.`;
    });
    list();
  }).catch(() => {status.textContent = '아래 전국센터·지점 목록에서 원하는 지역을 선택해 주세요.';});
})();
