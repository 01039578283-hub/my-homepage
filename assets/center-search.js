(function () {
  function normalize(value) {
    return (value || "").toString().trim().toLocaleLowerCase("ko-KR");
  }

  function kindLabel(kind) {
    if (kind === "region") return "권역";
    if (kind === "district") return "지역";
    return "학원";
  }

  function localName(title) {
    return (title || "")
      .replace(/\s*영어\s*수학\s*학원\s*$/g, "")
      .trim();
  }

  function createPillList(items, options) {
    var list = document.createElement("div");
    list.className = "center-local-list";

    var shown = items.slice(0, options.limit || 10);
    shown.forEach(function (item) {
      var pill = document.createElement("span");
      pill.className = "center-local-pill";
      pill.textContent = options.label(item);
      list.appendChild(pill);
    });

    if (!shown.length) {
      var empty = document.createElement("span");
      empty.className = "center-local-pill muted";
      empty.textContent = options.emptyText || "준비 중";
      list.appendChild(empty);
    }

    if (items.length > shown.length) {
      var more = document.createElement("span");
      more.className = "center-local-pill more";
      more.textContent = "+" + (items.length - shown.length);
      list.appendChild(more);
    }

    return list;
  }

  function createResultCard(item) {
    var link = document.createElement("a");
    link.className = "center-result-card";
    link.href = item.url;
    link.dataset.kind = item.kind;

    var meta = document.createElement("span");
    meta.className = "center-result-meta";
    meta.textContent = kindLabel(item.kind) + " · " + item.parent;

    var title = document.createElement("strong");
    title.textContent = item.title;

    var action = document.createElement("em");
    action.textContent = "페이지 보기";

    link.appendChild(meta);
    link.appendChild(title);
    link.appendChild(action);
    return link;
  }

  function createRegionPageCard(region) {
    var link = document.createElement("a");
    link.className = "center-result-card center-region-page-card";
    link.href = region.url;
    link.dataset.kind = "region";

    var meta = document.createElement("span");
    meta.className = "center-result-meta";
    meta.textContent = "권역 안내 · 전국센터";

    var title = document.createElement("strong");
    title.textContent = region.title;

    var desc = document.createElement("p");
    desc.className = "center-result-desc";
    desc.textContent = region.title + "에 있는 와와학습코칭학원의 정보를 확인할 수 있습니다✨";

    var action = document.createElement("em");
    action.textContent = region.title + " 바로가기";

    link.appendChild(meta);
    link.appendChild(title);
    link.appendChild(desc);
    link.appendChild(action);
    return link;
  }

  function createRegionCard(region, districts) {
    var link = document.createElement("a");
    link.className = "center-result-card center-region-summary-card";
    link.href = region.url;
    link.dataset.kind = "region";

    var meta = document.createElement("span");
    meta.className = "center-result-meta";
    meta.textContent = "권역 · 전국센터";

    var title = document.createElement("strong");
    title.textContent = region.title;

    var list = createPillList(districts, {
      limit: 12,
      emptyText: "지역 준비 중",
      label: function (item) {
        return item.title;
      },
    });

    var action = document.createElement("em");
    action.textContent = region.title + " 센터 보기";

    link.appendChild(meta);
    link.appendChild(title);
    link.appendChild(list);
    link.appendChild(action);
    return link;
  }

  function createDistrictCard(district, locals) {
    var link = document.createElement("a");
    link.className = "center-result-card center-district-card";
    link.href = district.url;
    link.dataset.kind = "district";

    var meta = document.createElement("span");
    meta.className = "center-result-meta";
    meta.textContent = "지역 · " + district.parent;

    var title = document.createElement("strong");
    title.textContent = district.title;

    var list = createPillList(locals, {
      limit: 10,
      emptyText: "하위 동네 준비 중",
      label: function (item) {
        return localName(item.title);
      },
    });

    var action = document.createElement("em");
    action.textContent = district.title + " 페이지 보기";

    link.appendChild(meta);
    link.appendChild(title);
    link.appendChild(list);
    link.appendChild(action);
    return link;
  }

  function regionGroups(index) {
    return index
      .filter(function (item) {
        return item.kind === "region";
      })
      .map(function (region) {
        return {
          region: region,
          districts: index.filter(function (item) {
            return item.kind === "district" && item.region === region.region;
          }),
        };
      });
  }

  function localsForDistrict(index, district) {
    var prefix = district.url.replace(/index\.html$/, "");
    return index.filter(function (item) {
      return item.kind === "local" && item.url.indexOf(prefix) === 0;
    });
  }

  function districtGroups(index, region) {
    return index
      .filter(function (item) {
        return item.kind === "district" && item.region === region;
      })
      .map(function (district) {
        return {
          district: district,
          locals: localsForDistrict(index, district),
        };
      });
  }

  function selectedRegion(index, region) {
    return index.find(function (item) {
      return item.kind === "region" && item.region === region;
    });
  }

  function queryDistrictGroups(index, query, activeRegion) {
    var matchedRegions = index
      .filter(function (item) {
        var regionMatch = activeRegion === "all" || item.region === activeRegion;
        return item.kind === "region" && regionMatch && normalize(item.search).indexOf(query) !== -1;
      })
      .map(function (item) {
        return item.region;
      });

    var seen = {};
    return index
      .filter(function (item) {
        var regionMatch = activeRegion === "all" || item.region === activeRegion;
        var directDistrictMatch = item.kind === "district" && normalize(item.search).indexOf(query) !== -1;
        var regionDistrictMatch = item.kind === "district" && matchedRegions.indexOf(item.region) !== -1;
        return regionMatch && (directDistrictMatch || regionDistrictMatch);
      })
      .filter(function (district) {
        if (seen[district.url]) return false;
        seen[district.url] = true;
        return true;
      })
      .map(function (district) {
        return {
          district: district,
          locals: localsForDistrict(index, district),
        };
      });
  }

  function initCenterSearch() {
    var index = window.WAWA_CENTER_INDEX || [];
    var input = document.querySelector("[data-center-search-input]");
    var form = document.querySelector("[data-center-search-form]");
    var chips = Array.prototype.slice.call(document.querySelectorAll("[data-center-region]"));
    var results = document.querySelector("[data-center-search-results]");
    var activeLabel = document.querySelector("[data-center-active-label]");
    var help = document.querySelector("[data-center-results-help]");
    var empty = document.querySelector("[data-center-search-empty]");

    if (!input || !results || !empty || !chips.length || !index.length) {
      return;
    }

    var activeRegion = "all";

    function selectedRegionLabel() {
      var selected = chips.find(function (chip) {
        return chip.dataset.centerRegion === activeRegion;
      });
      return selected ? selected.textContent : "전체";
    }

    function filteredItems() {
      var query = normalize(input.value);
      return index.filter(function (item) {
        var regionMatch = activeRegion === "all" || item.region === activeRegion;
        var queryMatch = !query || normalize(item.search).indexOf(query) !== -1;
        return regionMatch && queryMatch;
      });
    }

    function render() {
      var rawQuery = input.value.trim();
      var query = normalize(rawQuery);
      var items = filteredItems();
      results.innerHTML = "";

      if (!query && activeRegion === "all") {
        var regions = regionGroups(index);
        regions.forEach(function (group) {
          results.appendChild(createRegionCard(group.region, group.districts));
        });
        items = regions;
        if (activeLabel) activeLabel.textContent = "전국 학원";
        if (help) help.textContent = "전국에 있는 와와학습코칭센터의 정보를 확인해보세요🤗";
      } else if (!query && activeRegion !== "all") {
        var region = selectedRegion(index, activeRegion);
        var groups = districtGroups(index, activeRegion);
        if (region) {
          results.appendChild(createRegionPageCard(region));
        }
        groups.forEach(function (group) {
          results.appendChild(createDistrictCard(group.district, group.locals));
        });
        items = region ? [region].concat(groups) : groups;
        if (activeLabel) activeLabel.textContent = selectedRegionLabel();
        if (help) help.textContent = "지역 카드 안에서 연결된 동네를 함께 확인할 수 있습니다.";
      } else {
        var districtMatches = queryDistrictGroups(index, query, activeRegion);
        if (districtMatches.length) {
          districtMatches.forEach(function (group) {
            results.appendChild(createDistrictCard(group.district, group.locals));
          });
          items = districtMatches;
          if (activeLabel) activeLabel.textContent = rawQuery + " 관련 지역";
          if (help) help.textContent = "검색어와 연결된 지역 카드에서 하위 동네를 함께 확인할 수 있습니다.";
        } else {
          items.forEach(function (item) {
            results.appendChild(createResultCard(item));
          });
          if (activeLabel) activeLabel.textContent = selectedRegionLabel() + " 검색 결과";
          if (help) help.textContent = "검색 결과를 선택하면 해당 센터 페이지로 이동합니다.";
        }
      }

      empty.hidden = items.length !== 0;
      results.hidden = items.length === 0;
    }

    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        activeRegion = chip.dataset.centerRegion;
        chips.forEach(function (item) {
          item.classList.toggle("active", item === chip);
          item.setAttribute("aria-pressed", item === chip ? "true" : "false");
        });
        render();
      });
    });

    input.addEventListener("input", render);

    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var first = results.querySelector("a");
        if (first) {
          window.location.href = first.href;
        }
      });
    }

    render();
  }

  document.addEventListener("DOMContentLoaded", initCenterSearch);
})();
