from __future__ import annotations

import hashlib
import html
import json
import random
import re
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CENTER_ROOT = ROOT / "center"
REFERENCE_DIR_NAME = "\ucc38\uace0\uc790\ub8cc"
COMMON_DIR_NAME = "\uacf5\ud1b5\uc790\ub8cc"
REVIEW_FILE_NAME = "\ud559\ubd80\ubaa8 \ud6c4\uae30.txt"
TODAY = date.today().isoformat()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def common_review_path() -> Path:
    root_parent = ROOT.parent
    reference = next(p for p in root_parent.iterdir() if p.name == REFERENCE_DIR_NAME)
    common = next(p for p in reference.iterdir() if p.name == COMMON_DIR_NAME)
    return next(p for p in common.iterdir() if p.name == REVIEW_FILE_NAME)


def parse_review_bank() -> list[str]:
    source = common_review_path().read_text(encoding="utf-8-sig")
    result: list[str] = []
    seen: set[str] = set()
    skip_tokens = [
        "수강생 학부모 후기",
        "할인",
        "환불",
        "결제",
        "카드",
        "현금",
        "계좌",
        "차량",
        "셔틀",
        "주차",
        "간식",
        "식사",
    ]
    for line in source.splitlines():
        text = clean_text(line)
        if len(text) < 12:
            continue
        if any(token in text for token in skip_tokens):
            continue
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def title_from_html(source: str) -> str:
    match = re.search(r"<title>(.*?)</title>", source, re.S | re.I)
    if match:
        title = clean_text(match.group(1)).split("|", 1)[0].strip()
        if title:
            return title
    match = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.S | re.I)
    return clean_text(match.group(1)) if match else ""


def breadcrumb_names(source: str) -> list[str]:
    script_re = re.compile(
        r'<script\b(?=[^>]*type=["\']application/ld\+json["\'])[^>]*>(.*?)</script>',
        re.S | re.I,
    )
    for raw in script_re.findall(source):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack: list[Any] = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("@type") == "BreadcrumbList":
                    return [
                        clean_text(str(item.get("name", "")))
                        for item in node.get("itemListElement", [])
                        if isinstance(item, dict) and item.get("name")
                    ]
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)
    return []


def page_context(page_dir: Path, source: str) -> dict[str, str]:
    rel = page_dir.relative_to(CENTER_ROOT)
    parts = rel.parts
    crumbs = breadcrumb_names(source)
    title = title_from_html(source)
    region = crumbs[1] if len(crumbs) > 1 else (parts[0] if len(parts) > 0 else "")
    district = crumbs[2] if len(crumbs) > 2 else (parts[1] if len(parts) > 1 else "")
    neighborhood = crumbs[3] if len(crumbs) > 3 else (parts[2] if len(parts) > 2 else "")
    if title:
        first_token = title.split()[0].strip()
        if first_token and not first_token.startswith("와와"):
            neighborhood = first_token
    return {
        "title": title,
        "region": region,
        "district": district,
        "neighborhood": neighborhood,
        "child": parts[3] if len(parts) > 3 else "",
        "rel": rel.as_posix(),
    }


def grade_label(title: str, child: str = "") -> str:
    text = f"{title} {child}"
    if any(token in text for token in ("고등", "고1", "고2", "고3", "highschool")):
        return "고등반"
    if any(token in text for token in ("중등", "중학생", "중1", "중2", "중3", "middleschool")):
        return "중등반"
    if any(token in text for token in ("초등", "초등학생", "초1", "초2", "초3", "초4", "초5", "초6", "elementary")):
        return "초등반"
    return "초·중·고"


def subject_label(title: str, child: str = "") -> str:
    text = f"{title} {child}"
    if any(token in text for token in ("국영수", "전과목", "all")):
        return "국어·영어·수학"
    if any(token in text for token in ("영수", "영어수학", "수학영어", "englishmath", "mathenglish")):
        return "영어·수학"
    if "영어" in text or "english" in text:
        return "영어"
    if "수학" in text or "math" in text:
        return "수학"
    if "국어" in text:
        return "국어"
    return "영어·수학"


def compatible_review(text: str, grade: str, subject: str) -> bool:
    if grade == "고등반" and any(token in text for token in ("초등학생", "초등반", "중학생", "중등반")):
        return False
    if grade == "중등반" and any(token in text for token in ("초등학생", "초등반", "고등학생", "고등반", "수능")):
        return False
    if grade == "초등반" and any(token in text for token in ("중학생", "중등반", "고등학생", "고등반", "수능", "내신")):
        return False
    if subject == "수학" and any(token in text for token in ("영어", "어휘", "독해", "문법", "국어")):
        return False
    if subject == "영어" and any(token in text for token in ("수학", "국어")):
        return False
    if subject == "국어" and any(token in text for token in ("수학", "영어")):
        return False
    return True


def pool_for(bank: list[str], tokens: list[str], grade: str, subject: str) -> list[str]:
    pool = []
    for review in bank:
        if any(token in review for token in tokens) and compatible_review(review, grade, subject):
            pool.append(review)
    return pool


def choose_reviews(bank: list[str], ctx: dict[str, str]) -> list[str]:
    seed = int(hashlib.sha256((ctx["rel"] + "|" + ctx["title"]).encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    grade = grade_label(ctx["title"], ctx["child"])
    subject = subject_label(ctx["title"], ctx["child"])
    pools = [
        pool_for(bank, ["성적", "점수", "시험", "개념", "기초", "실력", "문제"], grade, subject),
        pool_for(bank, ["오답", "복습", "숙제", "과제", "계획", "진도", "관리", "피드백"], grade, subject),
        pool_for(bank, ["선생님", "설명", "질문", "친절", "눈높이", "수업 분위기"], grade, subject),
        pool_for(bank, ["상담", "학부모", "소통", "안내", "방향", "고민"], grade, subject),
        pool_for(bank, ["습관", "자신감", "집중", "흥미", "동기", "태도", "스스로"], grade, subject),
        pool_for(bank, ["교실", "위치", "자료", "운영", "시간", "환경", "반별"], grade, subject),
    ]
    selected: list[str] = []
    used: set[str] = set()
    for pool in pools:
        candidates = [review for review in pool if review not in used]
        if not candidates:
            candidates = [review for review in bank if review not in used and compatible_review(review, grade, subject)]
        if not candidates:
            candidates = [review for review in bank if review not in used]
        if not candidates:
            break
        review = rng.choice(candidates)
        selected.append(review)
        used.add(review)
    while len(selected) < 6:
        candidates = [review for review in bank if review not in used and compatible_review(review, grade, subject)]
        if not candidates:
            candidates = [review for review in bank if review not in used]
        if not candidates:
            break
        review = rng.choice(candidates)
        selected.append(review)
        used.add(review)
    return selected[:6]


def normalize_base_review(review: str) -> str:
    review = clean_text(review)
    review = review.rstrip(" .")
    return review + "."


def contextual_review(base: str, ctx: dict[str, str], index: int) -> str:
    title = ctx["title"] or "와와학습코칭센터"
    region = ctx["region"]
    district = ctx["district"]
    neighborhood = ctx["neighborhood"] or title.split()[0]
    grade = grade_label(title, ctx["child"])
    subject = subject_label(title, ctx["child"])
    base = normalize_base_review(base)
    seed = int(
        hashlib.sha256((ctx["rel"] + "|" + str(index) + "|" + base).encode("utf-8")).hexdigest()[:16],
        16,
    )
    rng = random.Random(seed)
    area = " ".join(part for part in [region, district, neighborhood] if part)
    prefixes = [
        f"{title} 상담을 받아보며 ",
        f"{area}에서 {subject} 학습 관리를 알아보다가 ",
        f"{neighborhood} {grade} 학습 흐름을 점검하면서 ",
        f"{title} 수업 방향을 확인한 뒤 ",
        f"{subject} 공부 습관을 다시 잡고 싶어 상담했는데, ",
        f"{neighborhood}에서 학원 선택을 고민하던 중 ",
    ]
    tails = [
        f" {title}을 찾는 학부모 입장에서 상담 전 궁금했던 부분이 훨씬 선명해졌습니다.",
        f" 특히 {grade} 학생에게 필요한 {subject} 진도와 오답 흐름을 함께 봐주는 점이 인상적이었습니다.",
        f" {neighborhood} 학생의 학교 진도와 평소 공부 습관을 함께 살펴보는 방식이라 안심됐습니다.",
        f" 단순한 진도 설명보다 아이에게 맞는 관리 기준을 잡아준 점이 좋았습니다.",
        f" 학부모가 집에서 확인해야 할 부분까지 정리되어 이후 관리 방향을 잡기 쉬웠습니다.",
        f" {area} 기준으로 가까운 학습 관리를 알아보는 가정에게 참고가 될 만한 상담이었습니다.",
    ]
    prefix = prefixes[index % len(prefixes)]
    tail = tails[(index + rng.randrange(len(tails))) % len(tails)]
    unique_tail = f" {title} 상담 기준으로 남긴 학부모 의견입니다."
    text = prefix + base + tail + unique_tail
    text = text.replace("..", ".")
    return clean_text(text)


def build_review_section(ctx: dict[str, str], reviews: list[str]) -> str:
    title = html.escape(ctx["title"])
    cards: list[str] = []
    for index, body in enumerate(reviews):
        rating = 4 if index == 5 else 5
        stars = "★★★★☆" if rating == 4 else "★★★★★"
        cards.append(
            "\n".join(
                [
                    '    <article class="parent-review-card">',
                    f'      <p class="parent-review-text">{html.escape(body)}</p>',
                    '      <div class="parent-review-meta">',
                    f'        <span class="parent-review-stars" aria-label="{rating}점 후기">{stars}</span>',
                    '        <span class="parent-review-name">학부모 후기</span>',
                    "      </div>",
                    "    </article>",
                ]
            )
        )
    return "\n".join(
        [
            '<section class="parent-review-section" aria-labelledby="parent-review-title">',
            '  <div class="parent-review-head">',
            '    <p class="parent-review-eyebrow">REAL PARENT REVIEWS</p>',
            f'    <h2 id="parent-review-title">{title} 학부모 후기</h2>',
            f'    <p>{title} 상담과 학습관리 과정에서 학부모님이 자주 언급하는 만족 포인트를 페이지 주제에 맞춰 정리했습니다.</p>',
            "  </div>",
            '  <div class="parent-review-grid">',
            *cards,
            "  </div>",
            "</section>",
        ]
    )


def schema_reviews(reviews: list[str]) -> list[dict[str, Any]]:
    result = []
    for index, body in enumerate(reviews):
        rating = "4" if index == 5 else "5"
        result.append(
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": "학부모"},
                "reviewBody": body,
                "reviewRating": {"@type": "Rating", "ratingValue": rating, "bestRating": "5"},
            }
        )
    return result


def update_json_reviews(data: Any, reviews: list[str]) -> bool:
    changed = False
    if isinstance(data, dict):
        if "review" in data and isinstance(data["review"], list):
            data["review"] = schema_reviews(reviews)
            data["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": "4.8",
                "bestRating": "5",
                "ratingCount": "6",
                "reviewCount": "6",
            }
            changed = True
        for value in data.values():
            if isinstance(value, (dict, list)):
                changed = update_json_reviews(value, reviews) or changed
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                changed = update_json_reviews(item, reviews) or changed
    return changed


def update_json_ld(source: str, reviews: list[str]) -> tuple[str, bool]:
    script_re = re.compile(
        r'(<script\b(?=[^>]*type=["\']application/ld\+json["\'])[^>]*>)(.*?)(</script>)',
        re.S | re.I,
    )
    changed_any = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed_any
        prefix, raw, suffix = match.groups()
        try:
            data = json.loads(raw)
        except Exception:
            return match.group(0)
        if not update_json_reviews(data, reviews):
            return match.group(0)
        changed_any = True
        return prefix + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + suffix

    return script_re.sub(replace, source), changed_any


def update_review_section(source: str, ctx: dict[str, str], reviews: list[str]) -> tuple[str, bool]:
    section_re = re.compile(r'<section class="parent-review-section"[\s\S]*?</section>', re.I)
    new_section = build_review_section(ctx, reviews)
    updated, count = section_re.subn(new_section, source, count=1)
    return updated, count == 1


def target_pages() -> list[Path]:
    pages: list[Path] = []
    for page in CENTER_ROOT.rglob("index.html"):
        rel_parts = page.parent.relative_to(CENTER_ROOT).parts
        if len(rel_parts) in (3, 4):
            pages.append(page)
    return sorted(pages)


def update_sitemap() -> bool:
    sitemap = ROOT / "sitemap.xml"
    if not sitemap.exists():
        return False
    source = sitemap.read_text(encoding="utf-8")

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        if "<loc>https://wawa-center.kr/center/" not in block:
            return block
        if "<lastmod>" in block:
            return re.sub(r"<lastmod>.*?</lastmod>", f"<lastmod>{TODAY}</lastmod>", block)
        return block.replace("</url>", f"<lastmod>{TODAY}</lastmod></url>")

    updated = re.sub(r"<url>.*?</url>", repl, source, flags=re.S)
    if updated != source:
        sitemap.write_text(updated, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> None:
    bank = parse_review_bank()
    if len(bank) < 6:
        raise SystemExit("review bank is too small")
    pages = target_pages()
    stats = {
        "bank": len(bank),
        "pages": len(pages),
        "section_updated": 0,
        "json_updated": 0,
        "unchanged": 0,
    }
    for page in pages:
        source = page.read_text(encoding="utf-8")
        ctx = page_context(page.parent, source)
        chosen = choose_reviews(bank, ctx)
        reviews = [contextual_review(base, ctx, index) for index, base in enumerate(chosen)]
        updated, section_changed = update_review_section(source, ctx, reviews)
        updated, json_changed = update_json_ld(updated, reviews)
        if updated != source:
            page.write_text(updated, encoding="utf-8", newline="\n")
        else:
            stats["unchanged"] += 1
        if section_changed:
            stats["section_updated"] += 1
        if json_changed:
            stats["json_updated"] += 1
    sitemap_changed = update_sitemap()
    print(json.dumps({**stats, "sitemap_changed": sitemap_changed}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
