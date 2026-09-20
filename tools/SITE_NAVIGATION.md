# 전체 상단 메뉴·로딩 정책

공통 메뉴 원본은 `tools/site_navigation.py`의 `NAV`와 `render_header`이고, 디자인은 `assets/header.css` 한 곳에서 관리합니다. 홈페이지, 전국센터, 지점안내, 과목별·학년별·교육정보의 메뉴 순서는 동일하며 활성 메뉴만 현재 경로에 맞춰 바뀝니다. 메뉴는 JavaScript 로딩 없이 HTML에 존재합니다.

## 페이지를 추가·재생성한 뒤

1. `python -B tools/refresh_center_course_names.py --write` — 기존 `/center/` 영어·수학 과정명을 초등학생·중학생·고등학생으로 정규화합니다. URL이나 다른 메뉴의 과정명은 바꾸지 않습니다.
2. `python -B tools/refresh_site_navigation.py --write`
3. 두 최종 정규화 스크립트를 각각 `--check`로 검사하고, `python -B tools/audit_public_internal_links.py`로 전체 내부링크를 확인합니다.
4. `python -B -m unittest discover -s tools -p "test_*.py"` 및 `node tools/test_center_search.cjs`를 실행합니다.
5. 모바일·데스크톱에서 기존 기능을 검수한 뒤, 사용자가 별도로 승인한 경우에만 배포합니다.

브랜치 페이지 생성기는 공통 메뉴 렌더러를 직접 호출합니다. 오래된 정적 생성기 출력도 위 최종 정규화 단계를 거쳐야 합니다. `--check`는 8개 메뉴 또는 기존 스타일/검색 데이터 참조가 다시 생기면 실패합니다. 각 실행의 검증 기록과 staging 사본은 공개 사이트 폴더 밖의 `CodexData/audit-output/wawa-site-navigation-20260920`에 저장됩니다.

## 용량·기능 보존

- 전국센터 검색 원본 `assets/center-search-data.js`는 유지합니다. 공개 페이지에는 `tools/compact_center_search.py`가 생성한 `assets/center-search-index.js`를 연결합니다. 중복 정보를 재조립하는 방식으로 6,025개 검색 항목의 모든 필드를 손실 없이 유지합니다. 기존 검색 데이터 생성기도 압축 전달본을 함께 갱신합니다.
- 메뉴용 JavaScript, 메뉴 HTML을 가져오는 추가 HTTP 요청, 새로운 외부 라이브러리는 없습니다.
- Noto 글꼴 및 굵기는 유지합니다. 개별 CSS의 반복 `@import` 대신 모든 페이지에서 하나의 글꼴 링크와 연결 준비만 사용합니다.
- 본문 이미지를 접거나 잘라내거나 변경하지 않습니다. 대표 이미지의 숨김 설정과 이미지 순서를 유지하고, 숨김 이미지·하단 지도에는 지연 로딩, 이미지에는 비동기 디코딩·누락된 크기 예약만 추가합니다.
- 제목, canonical, 메타 설명, JSON-LD, 본문, 이미지 경로·ALT, 지점 사실, sitemap/RSS 날짜를 바꾸지 않습니다.
- 검색 데이터 용량 절감 수치는 파일 및 gzip 크기의 비교이며, 실제 방문자의 전체 페이지 속도 개선률과 동일하지 않습니다.
