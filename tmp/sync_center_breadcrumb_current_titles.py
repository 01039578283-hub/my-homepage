from __future__ import annotations

import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENTER_ROOT = ROOT / "center"

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)
NAV_RE = re.compile(
    r'(<nav class="breadcrumb-nav"[^>]*>.*?'
    r'<span[^>]*aria-current="page"[^>]*>)(.*?)(</span>.*?</nav>)',
    re.I | re.S,
)
JSON_LD_RE = re.compile(
    r'(<script[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)',
    re.I | re.S,
)


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def current_title(source: str) -> str:
    match = TITLE_RE.search(source)
    if not match:
        return ""
    return clean_text(match.group(1)).split("|", 1)[0].strip()


def update_json_ld(source: str, title: str) -> tuple[str, bool]:
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        raw = match.group(2)
        if "BreadcrumbList" not in raw:
            return match.group(0)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)

        nodes = (
            data.get("@graph", [])
            if isinstance(data, dict) and isinstance(data.get("@graph"), list)
            else [data]
        )
        script_changed = False
        for node in nodes:
            if not isinstance(node, dict) or node.get("@type") != "BreadcrumbList":
                continue
            items = node.get("itemListElement")
            if not isinstance(items, list) or not items:
                continue
            if items[-1].get("name") != title:
                items[-1]["name"] = title
                script_changed = True

        if not script_changed:
            return match.group(0)
        changed = True
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"{match.group(1)}{encoded}{match.group(3)}"

    return JSON_LD_RE.sub(replace, source), changed


def update_page(page: Path) -> tuple[bool, str]:
    source = page.read_text(encoding="utf-8", errors="ignore")
    title = current_title(source)
    if not title:
        return False, "missing-title"

    nav_match = NAV_RE.search(source)
    if not nav_match:
        return False, "missing-nav"

    visible = clean_text(nav_match.group(2))
    nav_changed = visible != title
    if nav_changed:
        source = NAV_RE.sub(
            lambda match: (
                f"{match.group(1)}{html.escape(title, quote=False)}{match.group(3)}"
            ),
            source,
            count=1,
        )

    source, json_changed = update_json_ld(source, title)
    if not nav_changed and not json_changed:
        return False, "unchanged"

    page.write_text(source, encoding="utf-8")
    return True, "updated"


def main() -> None:
    pages = sorted(CENTER_ROOT.rglob("index.html"))
    result = {"updated": 0, "unchanged": 0, "missing-title": 0, "missing-nav": 0}
    for page in pages:
        changed, status = update_page(page)
        result[status] += 1
        if changed and status != "updated":
            raise RuntimeError(f"Unexpected status for {page}: {status}")
    print(f"pages={len(pages)} " + " ".join(f"{key}={value}" for key, value in result.items()))


if __name__ == "__main__":
    main()
