from __future__ import annotations

import hashlib
import html
import json
import random
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENTER_ROOT = ROOT / "center"
FAQ_BANK = ROOT.parent / "참고자료" / "공통자료" / "FAQ.txt"
TODAY = date.today().isoformat()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_faq_bank() -> list[tuple[str, str]]:
    source = FAQ_BANK.read_text(encoding="utf-8", errors="ignore")
    pairs = re.findall(r"질문:\s*(.*?)\s*답변:\s*(.*?)(?=\s*질문:|\Z)", source, re.S)
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    skip_tokens = [
        "할인",
        "환불",
        "결제",
        "카드",
        "현금",
        "영수증",
        "계좌",
        "차량",
        "셔틀",
        "주차",
        "간식",
        "식사",
    ]
    for question, answer in pairs:
        q = clean_text(question)
        a = clean_text(answer)
        if not q or not a:
            continue
        joined = q + " " + a
        if any(token in joined for token in skip_tokens):
            continue
        key = (q, a)
        if key not in seen:
            result.append(key)
            seen.add(key)
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
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', source, re.S | re.I):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("@type") == "BreadcrumbList":
                    return [
                        str(item.get("name", "")).strip()
                        for item in node.get("itemListElement", [])
                        if isinstance(item, dict) and item.get("name")
                    ]
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)
    return []


def page_context(page_dir: Path, source: str) -> dict:
    rel = page_dir.relative_to(CENTER_ROOT)
    parts = rel.parts
    crumbs = breadcrumb_names(source)
    return {
        "title": title_from_html(source),
        "region": crumbs[1] if len(crumbs) > 1 else (parts[0] if len(parts) > 0 else ""),
        "district": crumbs[2] if len(crumbs) > 2 else (parts[1] if len(parts) > 1 else ""),
        "neighborhood": crumbs[3] if len(crumbs) > 3 else (parts[2] if len(parts) > 2 else ""),
        "child": parts[3] if len(parts) > 3 else "",
        "rel": rel.as_posix(),
    }


def grade_label(title: str, child: str = "") -> str:
    text = f"{title} {child}"
    if any(token in text for token in ("고등", "고1", "고2", "고3", "highschool")):
        return "고등반"
    if any(token in text for token in ("중등", "중학생", "중1", "중2", "중3", "middleschool")):
        return "중등반"
    if any(token in text for token in ("초등", "초등학생", "초3", "초4", "초5", "초6", "elementary")):
        return "초등반"
    return "초등·중등·고등"


def subject_label(title: str, child: str = "") -> str:
    text = f"{title} {child}"
    if any(token in text for token in ("국영수", "전과목", "all")):
        return "국어·영어·수학"
    if any(token in text for token in ("영수", "수학영어", "영어수학", "영어 수학", "영어·수학", "englishmath", "mathenglish")):
        return "영어·수학"
    if "english" in text or "영어" in text:
        return "영어"
    if "math" in text or "수학" in text:
        return "수학"
    return "영어·수학"


def focus_sentence(subject: str) -> str:
    if subject == "수학":
        return "개념 이해, 유형 풀이, 반복 오답, 시험 전 복습 순서"
    if subject == "영어":
        return "어휘·문법·독해 흐름, 학교별 시험 범위, 지문 분석"
    if subject == "국어·영어·수학":
        return "국어 독해, 영어 어휘·문법, 수학 개념·유형"
    return "영어와 수학의 과목별 약점, 현재 진도, 오답 흐름"


def compatible_with_grade(pair: tuple[str, str], grade: str) -> bool:
    text = " ".join(pair)
    if grade == "고등반":
        return not any(token in text for token in ("초등학생", "초등 저학년", "초등 고학년", "초등반", "중학생", "중등반"))
    if grade == "중등반":
        return not any(token in text for token in ("초등학생", "초등 저학년", "초등 고학년", "초등반", "고등학생", "고등반", "수능"))
    if grade == "초등반":
        return not any(token in text for token in ("중학생", "중등반", "고등학생", "고등반", "수능", "내신"))
    return True


def normalize_grade_terms(text: str, grade: str) -> str:
    if grade == "고등반":
        return (
            text.replace("초등학생", "고등학생")
            .replace("중학생", "고등학생")
            .replace("초등반", "고등반")
            .replace("중등반", "고등반")
        )
    if grade == "중등반":
        return (
            text.replace("초등학생", "중학생")
            .replace("고등학생", "중학생")
            .replace("초등반", "중등반")
            .replace("고등반", "중등반")
        )
    if grade == "초등반":
        return (
            text.replace("중학생", "초등학생")
            .replace("고등학생", "초등학생")
            .replace("중등반", "초등반")
            .replace("고등반", "초등반")
        )
    return text


def pool_for(bank: list[tuple[str, str]], tokens: list[str]) -> list[tuple[str, str]]:
    pool = []
    for q, a in bank:
        joined = q + " " + a
        if any(token in joined for token in tokens):
            pool.append((q, a))
    return pool


def choose_pairs(bank: list[tuple[str, str]], ctx: dict) -> list[tuple[str, str]]:
    seed = int(hashlib.sha256((ctx["rel"] + "|" + ctx["title"]).encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    pools = [
        pool_for(bank, ["상담", "방문", "온라인", "등록"]),
        pool_for(bank, ["레벨테스트", "진단", "수준", "평가", "반 배정"]),
        pool_for(bank, ["수업", "과제", "숙제", "오답", "복습", "피드백", "관리"]),
        pool_for(bank, ["시험", "내신", "학교", "진도", "성적"]),
        pool_for(bank, ["학부모", "학생", "습관", "질문", "적응", "집중"]),
    ]
    grade = grade_label(ctx["title"], ctx["child"])
    selected: list[tuple[str, str]] = []
    used: set[tuple[str, str]] = set()
    for pool in pools:
        candidates = [pair for pair in pool if pair not in used and compatible_with_grade(pair, grade)]
        if not candidates:
            candidates = [pair for pair in bank if pair not in used and compatible_with_grade(pair, grade)]
        if not candidates:
            candidates = [pair for pair in pool if pair not in used]
        if not candidates:
            break
        pair = rng.choice(candidates)
        selected.append(pair)
        used.add(pair)
    while len(selected) < 5:
        candidates = [pair for pair in bank if pair not in used and compatible_with_grade(pair, grade)]
        if not candidates:
            candidates = [pair for pair in bank if pair not in used]
        if not candidates:
            break
        pair = rng.choice(candidates)
        selected.append(pair)
        used.add(pair)
    return selected[:5]


def contextual_question(question: str, ctx: dict, index: int) -> str:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title, ctx["child"])
    grade = grade_label(title, ctx["child"])
    q = clean_text(question)
    q = normalize_grade_terms(q, grade)
    q = re.sub(r"^학원\s+", "", q)
    def finish(text: str) -> str:
        text = text.replace("수업하나요", "수업을 진행하나요")
        text = text.replace("관리하나요", "관리하나요")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    if index == 0:
        if "상담" in q and q.startswith("상담"):
            return finish(f"{title}은 {q}")
        if "상담" in q:
            return finish(q.replace("상담", f"{title} 상담", 1))
        if "수업" in q:
            return finish(q.replace("수업", f"{title} 수업", 1))
        return finish(f"{title}은 {q}")
    if index == 1:
        if "수업" in q:
            return finish(q.replace("수업", f"{grade} {subject} 수업", 1))
        if "학생" in q:
            return finish(q.replace("학생", f"{grade} 학생", 1))
        return finish(f"{area}에서 {subject} 학습을 볼 때 {q}")
    if index == 2:
        if "오답" in q or "복습" in q or "과제" in q or "숙제" in q:
            return finish(f"{subject} 관리에서 {q}")
        if "레벨테스트" in q or "진단" in q or "평가" in q:
            return finish(f"{grade} {subject} 진단은 {q}")
        return finish(f"{grade} 기준으로 {q}")
    if index == 3:
        if q.startswith(area):
            return finish(q)
        return finish(f"{area}에서 {q}")
    if "학생" in q:
        return finish(q.replace("학생", f"{area} 학생", 1))
    return finish(f"{area} 학습 상담에서는 {q}")


def contextual_answer(answer: str, ctx: dict, index: int) -> str:
    title = ctx["title"]
    area = ctx["neighborhood"]
    subject = subject_label(title, ctx["child"])
    grade = grade_label(title, ctx["child"])
    focus = focus_sentence(subject)
    base = normalize_grade_terms(clean_text(answer), grade)
    tails = [
        f"{title} 상담에서는 {area} 학생의 {subject} 학습 상태와 {grade} 관리 기준을 함께 확인합니다.",
        f"{area}에서 {subject} 수업을 비교할 때도 현재 교재, 학교 진도, 반복 오답, 시험 범위를 함께 보는 것이 좋습니다.",
        f"{grade} 학생은 수업 후 다음 항목이 플래너와 오답 재학습으로 이어지는지 확인하면 도움이 됩니다: {focus}.",
        f"상담 시에는 {area} 학생의 생활 패턴과 학교 진도, 숙제 수행 정도를 함께 살펴 개별 관리 방향을 정리합니다.",
        f"학부모님은 {title} 상담 과정에서 수업 내용뿐 아니라 이후 관리 방식과 피드백 흐름까지 확인할 수 있습니다.",
    ]
    tail = tails[index % len(tails)]
    if base.endswith("."):
        return f"{base} {tail}"
    return f"{base}. {tail}"


def build_faqs(bank: list[tuple[str, str]], ctx: dict) -> list[dict]:
    result = []
    for index, (question, answer) in enumerate(choose_pairs(bank, ctx)):
        result.append(
            {
                "question": contextual_question(question, ctx, index),
                "answer": contextual_answer(answer, ctx, index),
            }
        )
    return result


def render_faq_section(ctx: dict, faqs: list[dict]) -> str:
    details = []
    for index, item in enumerate(faqs):
        open_attr = " open" if index == 0 else ""
        details.append(
            f"""    <details class="parent-faq-item"{open_attr}>
      <summary><span class="parent-faq-q">Q</span>{html.escape(item["question"])}</summary>
      <p class="parent-faq-answer">{html.escape(item["answer"])}</p>
    </details>"""
        )
    return f"""<section class="parent-faq-section" aria-labelledby="parent-faq-title">
  <div class="parent-faq-head">
    <p class="parent-faq-eyebrow">PARENT FAQ</p>
    <h2 id="parent-faq-title">{html.escape(ctx['title'])} FAQ</h2>
    <p>{html.escape(ctx['title'])} 상담 전 학부모님이 자주 확인하는 내용을 페이지 주제에 맞춰 정리했습니다.</p>
  </div>
  <div class="parent-faq-list">
{chr(10).join(details)}
  </div>
</section>"""


def replace_faq_section(source: str, ctx: dict, faqs: list[dict]) -> str:
    pattern = re.compile(r'<section\s+class=["\']parent-faq-section["\'][\s\S]*?</section>', re.I)
    replacement = render_faq_section(ctx, faqs)
    if not pattern.search(source):
        return source
    return pattern.sub(replacement, source, count=1)


def update_json_ld_faq(source: str, faqs: list[dict]) -> str:
    scripts = list(re.finditer(r'<script([^>]*)type=["\']application/ld\+json["\']([^>]*)>(.*?)</script>', source, re.S | re.I))
    updated = source
    faq_entities = [
        {
            "@type": "Question",
            "name": item["question"],
            "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
        }
        for item in faqs
    ]
    for match in reversed(scripts):
        raw = match.group(3)
        try:
            data = json.loads(raw)
        except Exception:
            continue
        touched = False

        def walk(node):
            nonlocal touched
            if isinstance(node, dict):
                typ = node.get("@type")
                if typ == "FAQPage" or (isinstance(typ, list) and "FAQPage" in typ):
                    node["mainEntity"] = faq_entities
                    touched = True
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        if touched:
            rendered = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            updated = updated[: match.start(3)] + rendered + updated[match.end(3) :]
    return updated


def touch_sitemap() -> int:
    sitemap = ROOT / "sitemap.xml"
    if not sitemap.exists():
        return 0
    source = sitemap.read_text(encoding="utf-8", errors="ignore")
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        block = match.group(0)
        if "https://wawa-center.kr/center/" not in block:
            return block
        count += 1
        if "<lastmod>" in block:
            return re.sub(r"<lastmod>.*?</lastmod>", f"<lastmod>{TODAY}</lastmod>", block, count=1)
        return block.replace("</url>", f"    <lastmod>{TODAY}</lastmod>\n  </url>")

    changed = re.sub(r"  <url>[\s\S]*?  </url>", repl, source)
    if changed != source:
        sitemap.write_text(changed, encoding="utf-8")
    return count


def main() -> None:
    bank = parse_faq_bank()
    if len(bank) < 20:
        raise SystemExit(f"FAQ bank too small: {len(bank)}")
    changed = 0
    targets = 0
    for index in CENTER_ROOT.rglob("index.html"):
        page_dir = index.parent
        rel = page_dir.relative_to(CENTER_ROOT)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth not in {3, 4}:
            continue
        source = index.read_text(encoding="utf-8", errors="ignore")
        ctx = page_context(page_dir, source)
        if not ctx["title"]:
            continue
        targets += 1
        faqs = build_faqs(bank, ctx)
        updated = replace_faq_section(source, ctx, faqs)
        updated = update_json_ld_faq(updated, faqs)
        if updated != source:
            index.write_text(updated, encoding="utf-8")
            changed += 1
    sitemap_count = touch_sitemap()
    print(json.dumps({"faq_bank": len(bank), "targets": targets, "changed": changed, "sitemap_urls_touched": sitemap_count, "date": TODAY}, ensure_ascii=False))


if __name__ == "__main__":
    main()
