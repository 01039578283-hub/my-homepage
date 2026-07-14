from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENTER_ROOT = ROOT / "center"


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


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
        stack = [data]
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


def page_context(page: Path, source: str) -> dict[str, str]:
    rel = page.parent.relative_to(CENTER_ROOT)
    parts = rel.parts
    crumbs = breadcrumb_names(source)
    title = title_from_html(source)
    region = crumbs[1] if len(crumbs) > 1 else (parts[0] if len(parts) > 0 else "")
    district = crumbs[2] if len(crumbs) > 2 else (parts[1] if len(parts) > 1 else "")
    neighborhood = crumbs[3] if len(crumbs) > 3 else (parts[2] if len(parts) > 2 else "")
    if title:
        first = title.split()[0].strip()
        if first and not first.startswith("와와"):
            neighborhood = first
    child = parts[3] if len(parts) > 3 else ""
    return {
        "title": title,
        "region": region,
        "district": district,
        "neighborhood": neighborhood,
        "child": child,
        "rel": rel.as_posix(),
    }


def grade_info(title: str, child: str) -> dict[str, str]:
    text = f"{title} {child}"
    if any(token in text for token in ("고등", "고1", "고2", "고3", "highschool")):
        return {
            "label": "고등반",
            "student": "고등학생",
            "concern": "내신과 모의고사 흐름, 단원별 개념 공백, 반복 오답",
            "goal": "시험 범위에 맞춘 개념 정리와 시간 배분",
            "prep": "최근 내신 시험지, 모의고사 오답, 현재 학교 진도, 사용하는 교재",
        }
    if any(token in text for token in ("중등", "중학생", "중1", "중2", "중3", "middleschool")):
        return {
            "label": "중등반",
            "student": "중학생",
            "concern": "학교 시험 범위, 수행평가 일정, 개념 누락과 반복 실수",
            "goal": "내신 대비와 기본기 보완을 함께 잡는 학습 루틴",
            "prep": "최근 학교 시험지, 수행평가 일정, 교과서 진도, 자주 틀리는 유형",
        }
    if any(token in text for token in ("초등", "초등학생", "초1", "초2", "초3", "초4", "초5", "초6", "elementary")):
        return {
            "label": "초등반",
            "student": "초등학생",
            "concern": "기초 개념, 읽기 습관, 숙제 수행, 공부를 시작하는 태도",
            "goal": "학습 습관과 기초 이해를 차근차근 잡는 관리",
            "prep": "현재 교재, 학교 진도, 숙제 수행 정도, 어려워하는 단원",
        }
    return {
        "label": "초·중·고",
        "student": "초등·중등·고등 학생",
        "concern": "학년별 진도, 과목별 약점, 공부 습관, 반복 오답",
        "goal": "학년과 과목에 맞는 진단 후 실행 가능한 학습 계획",
        "prep": "현재 교재, 최근 시험지, 학교 진도, 평소 공부 시간",
    }


def subject_info(title: str, child: str) -> dict[str, str]:
    text = f"{title} {child}"
    if any(token in text for token in ("국영수", "전과목", "all")):
        return {
            "label": "국어·영어·수학",
            "focus": "국어 독해, 영어 어휘·문법, 수학 개념·유형을 나누어 확인하는 종합 관리",
            "question": "과목별로 무엇이 막히는지",
            "after": "국어 독해 흐름, 영어 문법·독해, 수학 개념·오답이 각각 플래너에 반영되는지",
        }
    if any(token in text for token in ("영수", "영어수학", "수학영어", "영어 수학", "englishmath", "mathenglish")):
        return {
            "label": "영어·수학",
            "focus": "영어 어휘·문법·독해와 수학 개념·유형 풀이를 함께 보는 균형 관리",
            "question": "영어와 수학 중 어느 과목의 약점이 더 큰지",
            "after": "영어 과제와 수학 오답이 같은 주간 플래너 안에서 균형 있게 관리되는지",
        }
    if "영어" in text or "english" in text:
        return {
            "label": "영어",
            "focus": "어휘, 문법, 독해, 지문 분석, 학교별 시험 범위까지 이어지는 영어 관리",
            "question": "어휘·문법·독해 중 어디에서 점수가 흔들리는지",
            "after": "어휘 암기, 문법 적용, 독해 지문 분석이 수업 후 과제로 이어지는지",
        }
    if "수학" in text or "math" in text:
        return {
            "label": "수학",
            "focus": "개념 이해, 유형 풀이, 반복 오답, 시험 전 복습 순서를 잡는 수학 관리",
            "question": "개념 이해와 문제 적용 중 어디에서 막히는지",
            "after": "개념 설명, 유형 풀이, 반복 오답 정리가 수업 후 재학습으로 이어지는지",
        }
    if "국어" in text:
        return {
            "label": "국어",
            "focus": "독해력, 문학·비문학 지문 이해, 서술형 답안 흐름을 보는 국어 관리",
            "question": "지문 이해와 답안 작성 중 어느 부분이 약한지",
            "after": "독해 기록과 서술형 피드백이 다음 학습 계획으로 이어지는지",
        }
    return {
        "label": "영어·수학",
        "focus": "영어와 수학의 현재 진도, 과목별 약점, 주간 실행 상태를 함께 보는 관리",
        "question": "현재 진도와 반복 오답이 어디에서 생기는지",
        "after": "과목별 과제와 오답 재학습이 주간 플래너로 연결되는지",
    }


def page_purpose(title: str, child: str) -> str:
    if child in ("wawa", "wawaacademy"):
        return "와와학습코칭 방식과 상담 흐름"
    if child in ("highschool", "middleschool", "elementaryschool"):
        return "학년별 학습관리 기준"
    if child in ("all", "englishmath", "mathenglish"):
        return "여러 과목을 함께 관리할 때의 우선순위"
    if "학원" in title:
        return f"{title} 선택 기준"
    return "학습관리 기준"


def stable_variant(ctx: dict[str, str], count: int) -> int:
    seed = hashlib.sha256((ctx["rel"] + "|" + ctx["title"]).encode("utf-8")).hexdigest()
    return int(seed[:8], 16) % count


def build_lead(ctx: dict[str, str], grade: dict[str, str], subject: dict[str, str]) -> str:
    title = ctx["title"]
    neighborhood = ctx["neighborhood"]
    area = " ".join(part for part in (ctx["region"], ctx["district"], neighborhood) if part)
    purpose = page_purpose(title, ctx["child"])
    variants = [
        (
            f"{title}을 찾는다면 먼저 {subject['question']}를 확인하는 것이 좋습니다. "
            f"{area} 기준으로 {grade['student']}에게 필요한 {subject['focus']}가 수업 후에도 이어지는지 살펴보면, "
            f"{purpose}을 더 현실적으로 판단할 수 있습니다."
        ),
        (
            f"{title} 상담 전에는 거리나 시간표만 보기보다 {grade['concern']}이 실제 관리되는지를 먼저 봐야 합니다. "
            f"이 페이지는 {neighborhood} 학생에게 필요한 {subject['label']} 학습 진단, 수업 이후 실행 점검, 상담 준비 기준을 한 번에 확인할 수 있도록 정리했습니다."
        ),
        (
            f"{title} 페이지에서는 {grade['student']}의 현재 수준을 먼저 파악하고, {subject['after']}를 중심으로 확인하면 좋습니다. "
            f"{area}에서 학원을 비교하는 학부모님이 상담 전에 놓치기 쉬운 기준을 {title}에 맞춰 정리했습니다."
        ),
        (
            f"{title}을 알아볼 때는 단순히 수업 횟수보다 학생의 약점이 진단되고, 그 결과가 플래너와 오답 재학습으로 이어지는지가 중요합니다. "
            f"{neighborhood} 기준으로 {grade['goal']}이 필요한 가정이라면 이 페이지의 상담 기준을 먼저 확인해 보세요."
        ),
        (
            f"{title} 검색으로 들어왔다면 가장 먼저 볼 부분은 {grade['student']}에게 필요한 {subject['label']} 관리가 얼마나 구체적인지입니다. "
            f"현재 교재와 학교 진도, 반복되는 오답을 함께 점검해야 {neighborhood} 학생에게 맞는 학습 방향을 잡기 쉽습니다."
        ),
    ]
    return variants[stable_variant(ctx, len(variants))]


def build_points(ctx: dict[str, str], grade: dict[str, str], subject: dict[str, str]) -> list[tuple[str, str]]:
    title = ctx["title"]
    neighborhood = ctx["neighborhood"]
    area = " ".join(part for part in (ctx["region"], ctx["district"], neighborhood) if part)
    variants = stable_variant(ctx, 4)
    first_titles = ["1. 현재 수준 먼저 확인", "1. 검색어와 학생 상황 맞추기", "1. 상담 전 핵심 진단", "1. 수업 대상과 목표 확인"]
    second_titles = ["2. 수업 이후 관리 흐름", "2. 플래너와 오답 재학습", "2. 과목별 실행 점검", "2. 진도보다 중요한 관리 방식"]
    third_titles = ["3. 상담 전 준비 자료", "3. 학부모가 확인할 자료", "3. 상담 정확도를 높이는 준비", "3. 맞춤 진단을 위한 체크"]
    return [
        (
            first_titles[variants],
            f"{title}에서는 {grade['student']}의 {subject['question']}를 먼저 확인해야 합니다. {area} 학생의 현재 교재, 학교 진도, 공부 습관을 함께 보면 상담 방향이 더 분명해집니다.",
        ),
        (
            second_titles[(variants + 1) % 4],
            f"{title} 선택 시에는 {subject['after']}를 확인하는 것이 중요합니다. 수업에서 끝나는 설명보다 이후 실행과 피드백이 이어져야 학습 변화가 보입니다.",
        ),
        (
            third_titles[(variants + 2) % 4],
            f"{title} 상담 전에는 {grade['prep']} 같은 자료를 준비하면 좋습니다. 자료가 구체적일수록 {neighborhood} 학생에게 필요한 보완 순서와 학습 계획을 더 정확히 잡을 수 있습니다.",
        ),
    ]


def build_section(ctx: dict[str, str]) -> str:
    title = ctx["title"]
    grade = grade_info(title, ctx["child"])
    subject = subject_info(title, ctx["child"])
    lead = build_lead(ctx, grade, subject)
    points = build_points(ctx, grade, subject)
    lines = [
        f'<section class="article-search-answer" aria-label="{html.escape(title)} 검색 의도 답변">',
        '  <p class="article-answer-kicker">검색 의도 바로 답변</p>',
        f'  <h2>{html.escape(title)}, 상담 전 먼저 확인할 기준</h2>',
        f'  <p class="article-answer-lead">{html.escape(lead)}</p>',
        '  <ul class="article-answer-points">',
    ]
    for heading, body in points:
        lines.append(f'    <li><span>{html.escape(heading)}</span><p>{html.escape(body)}</p></li>')
    lines.extend(["  </ul>", "</section>"])
    return "\n".join(lines)


def target_pages() -> list[Path]:
    pages: list[Path] = []
    for page in CENTER_ROOT.rglob("index.html"):
        parts = page.parent.relative_to(CENTER_ROOT).parts
        if len(parts) in (3, 4):
            pages.append(page)
    return sorted(pages)


def main() -> None:
    section_re = re.compile(r'<section class="article-search-answer"[\s\S]*?</section>', re.I)
    stats = {"pages": 0, "updated": 0, "missing_section": 0}
    for page in target_pages():
        source = page.read_text(encoding="utf-8")
        ctx = page_context(page, source)
        if not ctx["title"]:
            stats["missing_section"] += 1
            continue
        new_section = build_section(ctx)
        updated, count = section_re.subn(new_section, source, count=1)
        stats["pages"] += 1
        if count != 1:
            stats["missing_section"] += 1
            continue
        if updated != source:
            page.write_text(updated, encoding="utf-8", newline="\n")
            stats["updated"] += 1
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
