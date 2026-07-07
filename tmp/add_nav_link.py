from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = [
    ROOT / "index.html",
    ROOT / "overview" / "index.html",
    ROOT / "교육정보" / "index.html",
    ROOT / "교육정보" / "초등학생-공부법" / "index.html",
    ROOT / "교육정보" / "중학생-공부법" / "index.html",
    ROOT / "교육정보" / "고등학생-공부법" / "index.html",
    ROOT / "교육정보" / "수학-공부법" / "index.html",
    ROOT / "교육정보" / "영어-공부법" / "index.html",
    ROOT / "교육정보" / "국어-공부법" / "index.html",
    ROOT / "교육정보" / "시험기간-공부법" / "index.html",
    ROOT / "교육정보" / "오답노트-작성법" / "index.html",
    ROOT / "교육정보" / "자기주도학습-방법" / "index.html",
    ROOT / "교육정보" / "학부모-상담-체크리스트" / "index.html",
]

PATTERN = re.compile(r'(<a[^>]*href=")([^"]*center/)("[^>]*>전국센터</a>)')


def fix_page(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    if "학부모후기/" in source:
        return False

    m = PATTERN.search(source)
    if not m:
        raise RuntimeError(f"전국센터 nav link not found in {path}")

    center_href = m.group(2)
    prefix = center_href[: -len("center/")]
    review_link = f'<a href="{prefix}학부모후기/">학부모후기</a>'

    updated = source[: m.start()] + review_link + source[m.start():]
    if updated == source:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    for f in FILES:
        print(f"{f.relative_to(ROOT)}: changed={fix_page(f)}")


if __name__ == "__main__":
    main()
