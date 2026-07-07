from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "https://wawa-center.kr"
ORG_NAME = "와와학습코칭센터"
PHONE = "010-3957-8283"
PHONE_INTL = "+82-10-3957-8283"


def build_org_node() -> dict:
    return {
        "@type": "EducationalOrganization",
        "@id": f"{DOMAIN}/#organization",
        "name": ORG_NAME,
        "alternateName": ["와와학습코칭학원", "와와센터", "와와"],
        "url": f"{DOMAIN}/",
        "logo": f"{DOMAIN}/assets/favicon.png",
        "image": f"{DOMAIN}/assets/title.png",
        "telephone": PHONE,
        "areaServed": {"@type": "Country", "name": "대한민국"},
        "description": "초등·중등·고등 영어·수학·국어 학습코칭을 안내하는 와와학습코칭센터 공식 홈페이지입니다.",
        "knowsAbout": ["학습코칭", "자기주도학습", "학습 플래너 관리", "오답 재학습", "내신 관리"],
        "contactPoint": {
            "@type": "ContactPoint",
            "telephone": PHONE_INTL,
            "contactType": "상담 문의",
            "availableLanguage": "Korean",
        },
    }


def build_website_node() -> dict:
    return {
        "@type": "WebSite",
        "@id": f"{DOMAIN}/#website",
        "url": f"{DOMAIN}/",
        "name": ORG_NAME,
        "inLanguage": "ko-KR",
        "publisher": {"@id": f"{DOMAIN}/#organization"},
    }


def process_home() -> None:
    path = ROOT / "index.html"
    source = path.read_text(encoding="utf-8")

    faq_pairs = [
        (
            "수업료는 어떻게 되나요?",
            "서울 지역 기준 1회 90~100분 수업으로 주 3~5회 등록 시 초등 249,000원~389,000원, 중등 266,000원~416,000원, 고등 299,000원~469,000원이며, 서울 외 지역은 이보다 낮게 책정됩니다. 정확한 금액은 지역과 수업 조건에 따라 상담 시 안내합니다.",
        ),
        (
            "어떤 학년부터 수강할 수 있나요?",
            "초등 1학년부터 중등, 고등 전 학년까지 상담 가능합니다. 지점별 개설 상황과 학생에게 적합한 코치 매칭 여부에 따라 안내가 달라질 수 있습니다.",
        ),
        (
            "학습 상황은 어떻게 공유되나요?",
            "수업 일지와 플래너 기록을 바탕으로 주간, 월간 단위 피드백을 제공합니다. 필요 시 전화 상담 또는 대면 상담으로 보호자님과 자세히 공유합니다.",
        ),
    ]

    m = re.search(r'(<script type="application/ld\+json">)(.*?)(</script>)', source, re.S)
    old_data = json.loads(m.group(2))
    breadcrumb = {
        "@type": "BreadcrumbList",
        "@id": f"{DOMAIN}/#breadcrumb",
        "itemListElement": old_data["itemListElement"],
    }

    graph = [
        build_website_node(),
        build_org_node(),
        {
            "@type": "WebPage",
            "@id": f"{DOMAIN}/#webpage",
            "url": f"{DOMAIN}/",
            "name": "와와학습코칭센터 영어수학 전문학원",
            "description": "초등, 중등, 고등 영어·수학 학습코칭을 안내하는 와와학습코칭센터 문의 홈페이지입니다.",
            "inLanguage": "ko-KR",
            "isPartOf": {"@id": f"{DOMAIN}/#website"},
            "publisher": {"@id": f"{DOMAIN}/#organization"},
            "breadcrumb": {"@id": f"{DOMAIN}/#breadcrumb"},
        },
        breadcrumb,
        {
            "@type": "FAQPage",
            "@id": f"{DOMAIN}/#faq",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_pairs
            ],
        },
    ]
    new_data = {"@context": "https://schema.org", "@graph": graph}
    new_jsonld = json.dumps(new_data, ensure_ascii=False, separators=(",", ":"))
    updated = source[: m.start()] + m.group(1) + new_jsonld + m.group(3) + source[m.end():]
    path.write_text(updated, encoding="utf-8")
    print("index.html updated")


def process_overview() -> None:
    path = ROOT / "overview" / "index.html"
    source = path.read_text(encoding="utf-8")

    m = re.search(r'(<script type="application/ld\+json">)(.*?)(</script>)', source, re.S)
    old_data = json.loads(m.group(2))
    breadcrumb_items = old_data["itemListElement"]
    breadcrumb_items[1]["item"] = f"{DOMAIN}/overview/"

    faq_pairs = [
        (
            "와와학습코칭센터는 다른 학원과 무엇이 다른가요?",
            "지식을 주입하는 수업이 아니라 학생이 스스로 학습 계획을 세우고 실행하는 힘을 기르는 코칭형 학습 관리를 제공합니다. 학습 플래너 작성, 메타인지 훈련, 월간 성장 리포트로 관리 흐름을 이어갑니다.",
        ),
        (
            "국어, 영어, 수학을 모두 지도하나요?",
            "네. 초등·중등·고등 학생을 대상으로 국어·영어·수학 3개 핵심 과목을 과목별 전문 코치진이 지도합니다.",
        ),
        (
            "상담은 어떻게 신청하나요?",
            "온라인 상담 신청 양식 또는 전화, 문자로 문의하시면 가까운 지점의 코칭 선생님이 학생의 학습 성향과 현재 상태를 확인한 뒤 안내해 드립니다.",
        ),
    ]

    graph = [
        {
            "@type": "WebPage",
            "@id": f"{DOMAIN}/overview/#webpage",
            "url": f"{DOMAIN}/overview/",
            "name": "학원소개 | 와와학습코칭센터 영어수학 전문학원",
            "description": "초등, 중등, 고등 영어·수학 학습코칭을 안내하는 와와학습코칭센터 문의 홈페이지입니다.",
            "inLanguage": "ko-KR",
            "isPartOf": {"@id": f"{DOMAIN}/#website"},
            "about": {"@id": f"{DOMAIN}/#organization"},
            "breadcrumb": {"@id": f"{DOMAIN}/overview/#breadcrumb"},
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{DOMAIN}/overview/#breadcrumb",
            "itemListElement": breadcrumb_items,
        },
        {
            "@type": "FAQPage",
            "@id": f"{DOMAIN}/overview/#faq",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_pairs
            ],
        },
    ]
    new_data = {"@context": "https://schema.org", "@graph": graph}
    new_jsonld = json.dumps(new_data, ensure_ascii=False, separators=(",", ":"))
    updated = source[: m.start()] + m.group(1) + new_jsonld + m.group(3) + source[m.end():]

    # Visible FAQ section to match the FAQPage schema added above
    faq_css = """
    .overview-faq { padding: 96px 0; }
    .overview-faq-list { display: grid; gap: 14px; margin-top: 12px; }
    .overview-faq-item { border: 1px solid rgba(217, 225, 236, 0.95); border-radius: 8px; background: rgba(255, 255, 255, 0.96); box-shadow: var(--shadow-soft); overflow: hidden; }
    .overview-faq-item summary { cursor: pointer; padding: 20px 24px; color: #0c1729; font-size: 17px; font-weight: 900; list-style: none; }
    .overview-faq-item summary::-webkit-details-marker { display: none; }
    .overview-faq-item p { margin: 0; padding: 0 24px 22px; color: #5f6b7a; font-size: 15px; line-height: 1.7; }
"""
    updated = updated.replace("  </style>", faq_css + "  </style>", 1)

    faq_html_items = "\n".join(
        f'          <details class="overview-faq-item"><summary>{q}</summary><p>{a}</p></details>'
        for q, a in faq_pairs
    )
    faq_section = f"""
        <section class="overview-faq">
            <div class="p-section-title">
                <h3>학원소개 자주 묻는 질문</h3>
                <p>학원 선택 전 보호자님들이 많이 궁금해하시는 내용을 정리했습니다.</p>
            </div>
            <div class="overview-faq-list">
{faq_html_items}
            </div>
        </section>
"""
    updated = updated.replace(
        '        <!-- 하단 신청 유도 CTA 배너 -->',
        faq_section + '\n        <!-- 하단 신청 유도 CTA 배너 -->',
        1,
    )

    path.write_text(updated, encoding="utf-8")
    print("overview/index.html updated")


if __name__ == "__main__":
    process_home()
    process_overview()
