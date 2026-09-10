# wawa-center.kr — 본사 자료 활용 모바일 업그레이드

## 상태

- 2026-09-11 로컬 검증 완료 후 사용자가 **공개 배포를 승인**했다. 이번 24파일만 기존 GitHub main과 Vercel 프로젝트에 반영한다.
- 최종 공개 배포 결과·배포 커밋·공개 URL 바이트 검증은 `C:\Users\1992k\Desktop\CodexData\tmp\wawa-learning-qa-20260911\release-verification.json` 및 바탕화면 작업 기록을 확인할 것. 이 소스 기록은 배포 직전 작성했다.
- 기준 공개 커밋: `244617da8d01b424bce8e539e2191244b8e746dc` (`01039578283-hub/my-homepage`). 이번 작업 시작 시 원격 main과 일치 확인.
- 실제 수정 소스: `C:\Users\1992k\Desktop\CodexData\tmp\wawa-hub-release-2026-09-10`.
- 브랜치: `codex/wawa-hubs-2026-09-10`. 기존 공개 버전의 별도 worktree를 이어 사용했다.
- `C:\Users\1992k\Desktop\홈페이지 정리\홈페이지`의 기존 미배포 파일과 Git index는 그대로 보존. 그 폴더는 공개본과 다르므로 전체 push/deploy/pull/reset을 하지 말 것.
- 로컬 확인: `http://127.0.0.1:8795/`, `http://127.0.0.1:8795/overview/`.
- 서버: 이 worktree에서 `python -m http.server 8795 --bind 127.0.0.1`.

## 변경 범위

기존 URL의 **메인·학원소개 2개 페이지**만 업그레이드. 기존 지역별 상세 페이지와 35개 허브 보강분은 수정하지 않았다.

- 메인: 브랜드 일러스트 히어로, 플랜·학습·생활 관리, 둥지형 학습 공간, 영상 3개, AI 영어·수학·국어·독서로 이동하는 카드.
- 학원소개: 4C 단계와 도식, 플래너·학습 자료·코칭 사진, AI 4과목 상세, 학년별 상담 준비, FAQ 6개.
- 기존 학원소개 원고의 과장된 성과/완벽 대비/반복 횟수/일률적 운영 단정 등을 본사 확인 사실과 상담 준비 안내로 교체했다. 특정 지점의 개설 여부·시설·성과를 단정하지 않는다.
- 기존 home H1 의미와 양쪽 title/canonical/og:url/og:image/소유확인 태그를 보존. description·og:description·WebPage 정보·hasPart·FAQ를 실제 본문과 맞췄다.
- 기존 상담 전화 `010-3957-8283`, 문자 링크·Google 상담 폼 링크, 수강료 금액/순서/수업 시간, 메인 13개 지역 링크 보존.
- 본사 이미지 10개 + 영상 썸네일 3개, 합계 13개 / 2,162,094바이트. 기존 코칭학원.com 작업에서 수집한 본사 원본 파일을 그대로 복사했고 바이트 일치 검증 완료.
- 이미지는 자르거나 접지 않음. 명시적 width/height와 비율 유지, 첫 히어로만 우선 로딩, 나머지는 lazy loading. AI 이미지도 로딩 전 공간을 예약하도록 폭을 지정해 레이아웃 이동을 방지.
- 사진은 본사 예시임을 캡션에 표시. 특정 센터의 현재 시설이라고 표현하지 않는다. AI 화면은 업데이트될 수 있음을 안내.
- scoped CSS `.wawa-upgrade`로 두 페이지만 변경. 본문 16px, 모바일 주제별 1열, AI 메뉴는 320px 1열/390px 2열. 메뉴 최소 44px, 상담 버튼 최소 46px. 모바일 하단 3열 버튼과 페이지 하단 안전 공간.
- 키보드 포커스 표시, 네이티브 FAQ, 기존 home FAQ aria-controls/aria-expanded·hidden 적용. JS가 없어도 원고와 YouTube 링크를 읽을 수 있음.
- 사이트맵 18,345개 URL/순서 유지, 메인·학원소개 lastmod만 2026-09-11. RSS는 교육정보 피드이므로 내용·바이트 유지.

## 본사 근거와 사용 원칙

2026-09-11 아래 공개 페이지 내용을 다시 확인했다.

- https://www.wawacenter.com/brand/wawacenter — 브랜드·둥지형 학습·본사 소개 영상.
- https://www.wawacenter.com/intro/coachingSystem — Check(맞춤 진단), Curriculum(맞춤 처방), Coaching(맞춤 지도), Consulting(맞춤 상담), 플랜/학습/생활 관리.
- https://www.wawacenter.com/intro/AISystem — AI 영어·수학 초1~고3, AI 국어 중1~고3, AI 독서 초1~중2. 실제 센터별 개설·이용 조건과 구분.
- 원본 이미지 폴더: `C:\Users\1992k\Desktop\홈페이지 정리\새 홈페이지3\assets\brand-upgrade-v1`. 수집 기록은 같은 프로젝트 `tools/data/brand-upgrade/source-manifest.json`. 원본 HTML 스냅샷·폼 토큰 등은 이 사이트에 복사하지 않음.
- `Main_CD_wawa.png`, `system_03.png`, `system_04.png`, `system_05.png`, `system_06_01.png`, `system_07_01.png`, `ais_step02.png`, `ais_math_content02.png`, `ais_kor_content03.png`, `ais_read_portfolio.png`을 사용.
- 본사 영상 ID: `avpJfW7eIV0`, `f_skFu40U04`, `UIXUaBZdNXU`. 실제 영상 제목과 구분해 중립적 카드 설명 사용. 학생 후기의 결과를 일반적 보장으로 표현하지 않는다.

## 검증

- `python scripts/render_learning_upgrade.py`: 두 페이지의 검토된 원고 조각을 반영. 공개 원본과 다르면 첫 실행 중단, 이후에는 표시된 블록만 교체. 날짜는 고정하여 재실행만으로 갱신되지 않도록 함.
- `python scripts/audit_learning_upgrade.py`: **199/199 PASS**. title/canonical/검증 태그/연락처/수강료/지역 링크 보존, JSON-LD·FAQ 일치, 이미지·내부 링크·목차 앵커·사이트맵·RSS·로컬 HTTP 검사.
- `node --check assets/learning-upgrade.js`: PASS.
- 인앱 브라우저: 320·390·768·1280px × 2페이지 = 8화면. 가로 넘침 0, 글씨 잘림 0, 44px 미만 주요 버튼 0, 이미지 비율/예약 공간 이상 0. 초기 iframe 0.
- FAQ 9개 클릭/Enter 열기·닫기 PASS. 320px 수강료 표 두 개 모두 가로 스크롤 없음. 메인→학원소개 4C 이동과 AI 수학 앵커 위치 확인.
- 영상 3개는 눌렀을 때 iframe 생성, 닫을 때 제거/썸네일 복원 PASS. **인앱에서는 iframe 영역이 빈 화면이라 실제 재생은 검증하지 못함.** 항상 제공되는 YouTube 직접 보기 링크와 재생 패널의 직접 열기/닫기 사용 가능. 실제 재생 완료라고 보고하면 안 됨.
- 외부 QA 기록: `C:\Users\1992k\Desktop\CodexData\tmp\wawa-learning-qa-20260911\static-audit.json`, `browser-qa.json`.

## 다음 수정·배포 시

- 원고 원본: `scripts/data/brand-upgrade-20260911/home.html`, `overview.html`.
- 스타일/동작: `assets/learning-upgrade.css`, `assets/learning-upgrade.js`.
- 정적 HTML 사이트이며 프레임워크 빌드·호스팅 이전은 하지 않음. `.openai/hosting.json` 없음.
- 이후 수정도 사용자 배포 요청 전에는 GitHub push/Vercel 배포 금지. 배포 시 원격 main 변동을 재확인하고 이번 범위 파일만 커밋. `.gitignore`의 scripts/__pycache__ 제외 규칙 포함, 기존 미배포 원본과 합치지 말 것.
