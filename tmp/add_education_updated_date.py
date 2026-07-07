from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    ROOT / "교육정보" / "index.html",
    ROOT / "교육정보" / "초등학생-공부법" / "index.html",
    ROOT / "교육정보" / "중학생-공부법" / "index.html",
    ROOT / "교육정보" / "고등학생-공부법" / "index.html",
]


def fix_page(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    if "edu-updated" in source:
        return False

    m = re.search(r'"dateModified":"(\d{4}-\d{2}-\d{2})"', source)
    date = m.group(1) if m else "2026-07-08"

    updated, count = re.subn(
        r"(</p>\s*<div class=\"edu-actions\">)",
        f'<p class="edu-updated">최종 업데이트 {date}</p>\\1',
        source,
        count=1,
    )
    if count == 0:
        raise RuntimeError(f"anchor not found in {path}")

    path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    for p in PAGES:
        print(f"{p.relative_to(ROOT)}: changed={fix_page(p)}")


if __name__ == "__main__":
    main()
