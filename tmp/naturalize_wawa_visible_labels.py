from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENTER = ROOT / "center"

REPLACEMENTS = [
    ("LOCAL ACADEMY GUIDE", "지역 학습 안내"),
    ("검색 의도 바로 답변", "상담 전 핵심 안내"),
    ("AI SUMMARY", "학습 안내 요약"),
    ("LOCAL STUDY SUMMARY", "지역 학습 안내"),
    ("PARENT FAQ", "자주 묻는 질문"),
    ("REAL PARENT REVIEWS", "학부모 상담 후기"),
    ("대표 키워드 기준 진단", "상담 전 진단 기준"),
    ("검색어와 학생상황 맞추기", "우리 아이에게 맞는지 확인하기"),
    ("검색 의도 답변", "상담 핵심 안내"),
    ("이라는 검색 의도에 맞춰", "을 알아보는 학생과 학부모님이 먼저 확인할 수 있도록"),
]

REGEX_REPLACEMENTS = []

CHECK_PATTERNS = [
    "LOCAL ACADEMY GUIDE",
    "검색 의도 바로 답변",
    "AI SUMMARY",
    "LOCAL STUDY SUMMARY",
    "PARENT FAQ",
    "REAL PARENT REVIEWS",
    "대표 키워드 기준 진단",
    "검색어와 학생상황 맞추기",
    "검색 의도에 맞춰",
]


def is_target_page(path: Path) -> bool:
    try:
        rel = path.relative_to(CENTER)
    except ValueError:
        return False
    parts = rel.parts
    return path.name == "index.html" and len(parts) >= 4


def update_file(path: Path) -> bool:
    source = path.read_text(encoding="utf-8", errors="ignore")
    updated = source
    for old, new in REPLACEMENTS:
        updated = updated.replace(old, new)
    for pattern, repl in REGEX_REPLACEMENTS:
        updated = pattern.sub(repl, updated)
    if updated != source:
        path.write_text(updated, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> None:
    targets = [p for p in CENTER.rglob("index.html") if is_target_page(p)]

    def process(path: Path) -> tuple[bool, dict[str, int]]:
        changed = update_file(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        counts = {pat: text.count(pat) for pat in CHECK_PATTERNS}
        return changed, counts

    changed = 0
    remaining: dict[str, int] = {pat: 0 for pat in CHECK_PATTERNS}
    with ThreadPoolExecutor(max_workers=24) as pool:
        for did_change, counts in pool.map(process, targets):
            if did_change:
                changed += 1
            for pat, count in counts.items():
                remaining[pat] += count

    print(
        json.dumps(
            {
                "targets": len(targets),
                "changed": changed,
                "remaining": remaining,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
