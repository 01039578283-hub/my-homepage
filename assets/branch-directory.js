(function () {
  "use strict";

  var input = document.querySelector("[data-branch-search-input]");
  var reset = document.querySelector("[data-branch-search-reset]");
  var cards = Array.prototype.slice.call(document.querySelectorAll("[data-branch-card]"));
  var status = document.querySelector("[data-branch-search-status]");
  var count = document.querySelector("[data-branch-count]");
  var empty = document.querySelector("[data-branch-empty]");

  if (!input || !cards.length) return;

  function normalize(value) {
    return String(value || "").toLocaleLowerCase("ko-KR").replace(/\s+/g, "").trim();
  }

  function applyFilter() {
    var query = normalize(input.value);
    var visible = 0;

    cards.forEach(function (card) {
      var match = !query || normalize(card.getAttribute("data-search")).indexOf(query) !== -1;
      card.hidden = !match;
      if (match) visible += 1;
    });

    if (reset) reset.disabled = !query;
    if (empty) empty.hidden = visible !== 0;
    if (count) count.textContent = visible + "개 센터를 표시하고 있습니다.";
    if (status) status.textContent = query ? "검색 결과 " + visible + "개" : "전체 센터 " + visible + "개";
  }

  input.addEventListener("input", applyFilter);
  input.addEventListener("search", applyFilter);

  if (reset) {
    reset.addEventListener("click", function () {
      input.value = "";
      applyFilter();
      input.focus();
    });
  }

  applyFilter();
})();
