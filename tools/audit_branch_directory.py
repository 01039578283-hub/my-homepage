"""Technical and content audit for the generated Korean branch directory."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

from lxml import html


ROOT = Path(__file__).resolve().parents[1]
BRANCH_ROOT = ROOT / "지점안내"
DOMAIN = "wawa-center.kr"
EXCLUDED_TERMS = ("(W+)", "글로리드", "대구역점2호관", "홍보 이미지")


def local_path_from_url(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc and parsed.netloc != DOMAIN:
        return None
    path = unquote(parsed.path or value.split("#", 1)[0])
    if not path.startswith("/"):
        return None
    relative = path.strip("/")
    target = ROOT / relative
    if path.endswith("/"):
        target = target / "index.html"
    return target


def main() -> None:
    files = sorted(BRANCH_ROOT.rglob("index.html"))
    errors: list[str] = []
    warnings: list[str] = []
    canonicals: list[str] = []
    titles: list[str] = []
    descriptions: list[str] = []
    branch_pages = 0
    region_pages = 0

    for file in files:
        relative = file.relative_to(ROOT).as_posix()
        raw = file.read_text(encoding="utf-8")
        document = html.fromstring(raw)
        title = "".join(document.xpath("//title/text()")).strip()
        description = "".join(document.xpath('//meta[@name="description"]/@content')).strip()
        canonical = "".join(document.xpath('//link[@rel="canonical"]/@href')).strip()
        h1s = [" ".join(item.text_content().split()) for item in document.xpath("//h1")]
        scripts = document.xpath('//script[@type="application/ld+json"]/text()')

        if not title:
            errors.append(f"{relative}: title 없음")
        if not description:
            errors.append(f"{relative}: meta description 없음")
        if len(h1s) != 1:
            errors.append(f"{relative}: H1 수 {len(h1s)}")
        if not canonical:
            errors.append(f"{relative}: canonical 없음")
        if not scripts:
            errors.append(f"{relative}: JSON-LD 없음")

        for script in scripts:
            try:
                data = json.loads(script)
            except json.JSONDecodeError as exc:
                errors.append(f"{relative}: JSON-LD 파싱 실패 {exc}")
                continue
            graph = data.get("@graph", []) if isinstance(data, dict) else []
            ids = [item.get("@id") for item in graph if isinstance(item, dict) and item.get("@id")]
            duplicates = [value for value, count in Counter(ids).items() if count > 1]
            if duplicates:
                errors.append(f"{relative}: JSON-LD @id 중복 {duplicates}")

            if len(file.relative_to(BRANCH_ROOT).parts) == 3:
                branch_pages += 1
                article = next((item for item in graph if item.get("@type") == "Article"), None)
                if not article:
                    errors.append(f"{relative}: Article 없음")
                elif article.get("abstract") != description:
                    errors.append(f"{relative}: Article abstract와 meta description 불일치")
                quick_answers = document.xpath('//section[contains(concat(" ", normalize-space(@class), " "), " branch-answer ")]//p[last()]/text()')
                if not quick_answers or " ".join(quick_answers[0].split()) != description:
                    errors.append(f"{relative}: 첫 요약과 meta description 불일치")
                media_sections = document.xpath('//section[contains(concat(" ", normalize-space(@class), " "), " branch-media ")]')
                if len(media_sections) != 1:
                    errors.append(f"{relative}: 학습 공간 이미지 섹션 수 {len(media_sections)}")
                else:
                    photo_source = media_sections[0].get("data-photo-source")
                    if photo_source not in {"center", "common"}:
                        errors.append(f"{relative}: 사진 출처 구분 없음")
                    media_images = media_sections[0].xpath('.//img')
                    if not media_images:
                        errors.append(f"{relative}: 학습 공간 이미지 없음")
                    if photo_source == "common" and "학습 공간과 운영 환경" not in media_sections[0].text_content():
                        errors.append(f"{relative}: 학습 공간 안내 문구 없음")
            elif len(file.relative_to(BRANCH_ROOT).parts) == 2:
                region_pages += 1

        for value in document.xpath("//img/@src"):
            target = local_path_from_url(value)
            if target is not None and not target.exists():
                errors.append(f"{relative}: 이미지 없음 {value}")
        for value in document.xpath("//a/@href"):
            target = local_path_from_url(value)
            if target is not None and not target.exists():
                errors.append(f"{relative}: 내부 링크 없음 {value}")

        for term in EXCLUDED_TERMS:
            if term in raw:
                errors.append(f"{relative}: 제외 표현 포함 {term}")

        if len(description) < 65 or len(description) > 165:
            warnings.append(f"{relative}: meta description 길이 {len(description)}")
        if len(title) > 65:
            warnings.append(f"{relative}: title 길이 {len(title)}")

        titles.append(title)
        descriptions.append(description)
        canonicals.append(canonical)

    duplicates = {
        "titles": [value for value, count in Counter(titles).items() if value and count > 1],
        "descriptions": [value for value, count in Counter(descriptions).items() if value and count > 1],
        "canonicals": [value for value, count in Counter(canonicals).items() if value and count > 1],
    }
    for kind, values in duplicates.items():
        if values:
            errors.append(f"중복 {kind}: {len(values)}")

    result = {
        "files": len(files),
        "branchPages": branch_pages,
        "regionPages": region_pages,
        "errors": errors,
        "warnings": warnings,
        "duplicateCounts": {key: len(value) for key, value in duplicates.items()},
    }
    report = ROOT / "reports" / "branch-directory" / "technical-audit.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
