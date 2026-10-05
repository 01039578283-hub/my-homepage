/* Local search and records: input values are never sent or automatically stored. */
(() => {
  "use strict";
  const normalize = value => value.normalize("NFKC").toLocaleLowerCase("ko").trim();
  const directory = document.querySelector("[data-guide-directory]");
  if (directory) {
    const search = directory.querySelector("[data-guide-search]");
    const audience = directory.querySelector("[data-guide-audience]");
    const buttons = [...directory.querySelectorAll("[data-category-filter]")];
    const cards = [...directory.querySelectorAll("[data-guide-card]")].map(element => ({
      element,
      category: element.dataset.category,
      audience: element.dataset.audience.split(" "),
      text: normalize(element.textContent)
    }));
    const groups = [...directory.querySelectorAll("[data-guide-group]")];
    let category = "all";
    const apply = () => {
      const terms = normalize(search.value).split(/\s+/).filter(Boolean);
      let count = 0;
      for (const card of cards) {
        const visible = (category === "all" || card.category === category) &&
          (audience.value === "all" || card.audience.includes(audience.value)) &&
          terms.every(term => card.text.includes(term));
        card.element.hidden = !visible;
        count += Number(visible);
      }
      for (const group of groups) {
        group.hidden = !group.querySelector("[data-guide-card]:not([hidden])");
      }
      directory.querySelector("[data-guide-count]").textContent = `${count}개의 가이드를 볼 수 있습니다.`;
      directory.querySelector("[data-guide-empty]").hidden = count > 0;
      for (const button of buttons) {
        button.setAttribute("aria-pressed", String(button.dataset.categoryFilter === category));
      }
    };
    search.addEventListener("input", apply);
    audience.addEventListener("change", apply);
    for (const button of buttons) {
      button.addEventListener("click", () => {
        category = button.dataset.categoryFilter;
        apply();
      });
    }
    for (const reset of directory.querySelectorAll("[data-reset-filters]")) {
      reset.addEventListener("click", () => {
        search.value = "";
        audience.value = "all";
        category = "all";
        apply();
      });
    }
    directory.querySelector("[data-guide-filters]").hidden = false;
    apply();
  }

  for (const form of document.querySelectorAll("[data-record-form]")) {
    const fields = [...form.querySelectorAll("textarea")];
    const status = form.querySelector("[data-record-status]");
    const labelFor = field => form.querySelector(`label[for="${field.id}"]`).textContent;
    form.addEventListener("submit", event => event.preventDefault());
    form.querySelector("[data-record-actions]").hidden = false;
    form.querySelector("[data-save-record]").addEventListener("click", () => {
      if (!fields.some(field => field.value.trim())) {
        status.textContent = "한 칸 이상 작성하거나 위의 빈 기록 양식을 내려받아 사용하세요.";
        fields[0].focus();
        return;
      }
      const now = new Date();
      const date = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(now);
      const body = `${form.dataset.title} · 학습 기록\n가이드: ${form.dataset.canonical}\n작성일: ${date}\n\n` +
        fields.map(field => {
          const hint = document.getElementById(field.getAttribute("aria-describedby")).textContent;
          return `${labelFor(field)}\n확인할 내용: ${hint}\n기록:\n${field.value || "(작성하지 않음)"}`;
        }).join("\n\n") + "\n";
      const blob = new Blob(["\uFEFF", body.replace(/\r?\n/g, "\r\n")], { type: "text/plain;charset=utf-8" });
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = form.dataset.filename.replace(/\.txt$/, "") + "-작성.txt";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      status.textContent = "작성한 내용을 TXT 파일로 내려받습니다. 저장한 파일에서 기록을 이어 볼 수 있습니다.";
    });
    form.addEventListener("reset", () => {
      status.textContent = "입력 내용을 비웠습니다. 이미 내려받은 파일은 그대로 남아 있습니다.";
    });
    form.querySelector("[data-print-record]").addEventListener("click", () => window.print());
  }
  const makePrintValues = () => {
    for (const field of document.querySelectorAll("[data-record-form] textarea")) {
      let mirror = field.parentElement.querySelector(".lg-print-value");
      if (!mirror) {
        mirror = document.createElement("p");
        mirror.className = "lg-print-value";
        field.after(mirror);
      }
      mirror.textContent = field.value || "(작성하지 않음)";
    }
  };
  window.addEventListener("beforeprint", makePrintValues);
  window.addEventListener("afterprint", () => {
    for (const mirror of document.querySelectorAll(".lg-print-value")) mirror.remove();
  });
})();
