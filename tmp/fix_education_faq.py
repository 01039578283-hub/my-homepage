from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    ROOT / "교육정보" / "index.html",
    ROOT / "교육정보" / "초등학생-공부법" / "index.html",
    ROOT / "교육정보" / "중학생-공부법" / "index.html",
    ROOT / "교육정보" / "고등학생-공부법" / "index.html",
    ROOT / "교육정보" / "시험기간-공부법" / "index.html",
    ROOT / "교육정보" / "수학-공부법" / "index.html",
    ROOT / "교육정보" / "영어-공부법" / "index.html",
    ROOT / "교육정보" / "학부모-상담-체크리스트" / "index.html",
    ROOT / "교육정보" / "오답노트-작성법" / "index.html",
    ROOT / "교육정보" / "자기주도학습-방법" / "index.html",
]


def fix_page(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    visible_pairs = re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", source)
    if not visible_pairs:
        raise RuntimeError(f"no visible FAQ found in {path}")

    m = re.search(r'(<script type="application/ld\+json">)(.*?)(</script>)', source, re.S)
    data = json.loads(m.group(2))
    faq_node = None
    for node in data["@graph"]:
        if node.get("@type") == "FAQPage":
            faq_node = node
            break
    if faq_node is None:
        raise RuntimeError(f"no FAQPage node found in {path}")

    faq_node["mainEntity"] = [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
        for q, a in visible_pairs
    ]

    new_jsonld = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    updated = source[: m.start()] + m.group(1) + new_jsonld + m.group(3) + source[m.end():]

    if updated != source:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> None:
    for p in PAGES:
        changed = fix_page(p)
        print(f"{p.relative_to(ROOT)}: changed={changed}")


if __name__ == "__main__":
    main()
