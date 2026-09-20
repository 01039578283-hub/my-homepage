"""Connect existing learning guides and reviewed branch pages without merging URLs.

This is a navigation-only postprocessor. It does not rewrite source manuscripts,
metadata, course eligibility, images or existing links. Run the scoped refresh
after a legacy subject-guide rebuild; branch-topic generation calls it directly.
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "https://wawa-center.kr"
STYLE = '/assets/branch-learning-routes.css?v=20260920'
STYLE_TAG = f'<link rel="stylesheet" href="{STYLE}">'
SCRIPT = re.compile(r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)', re.S)


def segment(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or value in (".", "..") or any(c in value for c in '/\\%?#<>\x00\r\n'):
        raise ValueError(f"안전하지 않은 경로 조각: {value!r}")
    return value


def canonical(path: str) -> str:
    return DOMAIN + quote(path, safe="/#")


def paired_routes(center: dict, item: dict, root: Path = ROOT) -> dict | None:
    if item["level"] != "고등" or item["subject"] not in ("수학", "영어"):
        return None
    locality = segment(item["locality"])
    region, name = segment(center["region"]), segment(center["routeName"])
    if locality not in center["neighborhoods"]:
        raise ValueError(f"센터와 동네가 일치하지 않습니다: {name}/{locality}")
    guide = f'/과목별학원/고등{item["subject"]}학원/{locality}/'
    if not (root / guide.strip("/") / "index.html").is_file():
        return None
    parent = f"/지점안내/{region}/{name}/"
    return {"guide": guide, "parent": parent, "child": parent + f'{locality}고등{item["subject"]}학원/'}


def block(content: str, position: str) -> str:
    return f'<!-- learning-routes:{position}:start -->\n{content}\n<!-- learning-routes:{position}:end -->\n'


def card(path: str, label: str, detail: str) -> str:
    return f'<a href="{escape(path, quote=True)}"><strong>{escape(label)}</strong><span>{escape(detail)}</span></a>'


def guide_label(item: dict) -> str:
    return f'{item["locality"]} 고등 {item["subject"]} 학습 선택 기준'


def bridge(center: dict, item: dict, routes: dict, kind: str, bottom: bool = False) -> str:
    position = "bottom" if bottom else "top"
    title_id = f"learning-route-{position}-title"
    if kind == "guide":
        heading = "학습 기준에서 실제 수업 확인까지" if not bottom else "학습 기준을 확인했다면, 수업 조건도 살펴보세요"
        text = "이 페이지는 학습 상태와 수업 선택 기준을 살펴보는 안내입니다. 학년·운영 조건과 방문 정보는 연결된 지점 안내에서 확인해 주세요."
        links = card(routes["child"] + "#overview", f'{center["routeName"]} 고등 {item["subject"]} 수업 확인', "제공 자료 기준 안내 학년과 별도 확인 조건")
        if not bottom:
            links += card(routes["parent"] + "#center-info", f'{center["routeName"]} 주소·센터 정보', "센터 위치와 전체 과목·학년 안내")
    else:
        heading = "수업 조건과 함께 살펴볼 학습 기준"
        text = "이 페이지에서는 연결 센터의 안내 학년과 수업 조건을 먼저 확인할 수 있습니다. 공부의 우선순위나 상담 질문을 정리하려면 학습 선택 안내를 함께 살펴보세요."
        links = card(routes["guide"], guide_label(item), "학습 상태 점검과 상담 전 살펴볼 질문")
    content = f'<nav class="learning-route-panel learning-route-panel--{kind}" id="learning-route-{position}" aria-labelledby="{title_id}"><div class="learning-route-inner"><h2 id="{title_id}">{escape(heading)}</h2>'
    if not bottom:
        content += f'<p>{escape(text)}</p>'
    content += f'<div class="learning-route-links">{links}</div></div></nav>'
    return block(content, position)


def change_graph(raw: str, kind: str, item: dict, routes: dict) -> str:
    matches = list(SCRIPT.finditer(raw))
    if len(matches) != 1:
        raise ValueError("JSON-LD 스크립트가 하나가 아닙니다.")
    match = matches[0]
    payload = json.loads(match.group(2))
    graph = payload["@graph"]
    page_nodes = [n for n in graph if n.get("@type") == "WebPage"]
    if len(page_nodes) != 1:
        raise ValueError("WebPage 노드를 확정할 수 없습니다.")
    destinations = [routes["child"], routes["parent"]] if kind == "guide" else [routes["guide"]]
    existing = page_nodes[0].get("relatedLink", [])
    if isinstance(existing, str):
        existing = [existing]
    page_nodes[0]["relatedLink"] = list(dict.fromkeys([*existing, *map(canonical, destinations)]))
    if kind == "child":
        lists = [n for n in graph if n.get("@id", "").endswith("#related-pages") and n.get("@type") == "ItemList"]
        if len(lists) != 1:
            raise ValueError("기존 관련 페이지 목록을 확정할 수 없습니다.")
        node = lists[0]
        elements = node["itemListElement"]
        if not any(entry.get("url") == canonical(routes["guide"]) for entry in elements):
            elements.append({"@type": "ListItem", "position": len(elements) + 1, "name": guide_label(item), "url": canonical(routes["guide"])})
        node["numberOfItems"] = len(elements)
    replacement = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return raw[:match.start(2)] + replacement + raw[match.end(2):]


def upgrade_page(raw: str, center: dict, item: dict, kind: str, root: Path = ROOT) -> str:
    if kind not in ("guide", "child"):
        raise ValueError(kind)
    routes = paired_routes(center, item, root)
    if routes is None:
        return raw
    doc = html.fromstring(raw)
    urls = doc.xpath('//link[@rel="canonical"]/@href')
    if len(urls) != 1 or urlsplit(urls[0]).netloc != "wawa-center.kr" or unquote(urlsplit(urls[0]).path) != routes[kind]:
        raise ValueError("페이지와 연결 대상의 canonical이 일치하지 않습니다.")
    if not doc.xpath(f'//link[@href="{STYLE}"]'):
        if raw.count("</head>") != 1:
            raise ValueError("head 닫힘 태그 오류")
        raw = raw.replace("</head>", STYLE_TAG + "\n</head>", 1)
    if 'id="learning-route-top"' not in raw:
        anchor = '<nav class="math-page-toc"' if kind == "guide" else '<section class="branch-primary-media"'
        if raw.count(anchor) != 1:
            raise ValueError("상단 연결 영역 삽입 위치 오류")
        raw = raw.replace(anchor, bridge(center, item, routes, kind) + anchor, 1)
    if kind == "guide":
        old_role = f'HIGH SCHOOL {"MATH" if item["subject"] == "수학" else "ENGLISH"} LOCAL GUIDE'
        new_role = f'고등 {item["subject"]} · 학습 선택 안내'
        if old_role in raw:
            raw = raw.replace(old_role, new_role, 1)
        elif new_role not in raw:
            raise ValueError("기존 학습 안내 역할 표시를 찾을 수 없습니다.")
        if 'id="learning-route-bottom"' not in raw:
            if raw.count("</main>") != 1:
                raise ValueError("main 닫힘 태그 오류")
            raw = raw.replace("</main>", bridge(center, item, routes, kind, bottom=True) + "</main>", 1)
    else:
        old_role = f'{escape(center["routeName"])} LEARNING GUIDE'
        new_role = f'{escape(center["routeName"])} · 센터별 수업 확인'
        if old_role in raw:
            raw = raw.replace(old_role, new_role, 1)
        elif new_role not in raw:
            raise ValueError("기존 지점 안내 역할 표시를 찾을 수 없습니다.")
        if 'data-learning-route="guide"' not in raw:
            pattern = r'(<div class="related-grid">)(.*?)(</div></section>)'
            matches = list(re.finditer(pattern, raw, re.S))
            if len(matches) != 1:
                raise ValueError("기존 관련 페이지 버튼 영역 오류")
            match = matches[0]
            added = card(routes["guide"], guide_label(item), "학습 상태와 상담 질문을 점검하는 안내").replace('<a ', '<a data-learning-route="guide" ', 1)
            raw = raw[:match.start(3)] + added + raw[match.start(3):]
    return change_graph(raw, kind, item, routes)
