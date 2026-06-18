import html
import os
import re
from pathlib import Path

ROOT = Path.cwd()
OVERVIEW = ROOT / "overview.html"


def rel_href(from_file: Path, target: Path) -> str:
    return os.path.relpath(target, start=from_file.parent).replace("\\", "/")


def about_summary(page_file: Path) -> str:
    overview_href = html.escape(rel_href(page_file, OVERVIEW))
    return f"""    <section class="center-section center-about-summary">
      <div class="center-about-copy">
        <p class="center-eyebrow summary-eyebrow">WAWA LEARNING COACHING</p>
        <h2>학생별 진단에서 시작하는 영어·수학 학습코칭</h2>
        <p>와와학습코칭센터는 초등, 중등, 고등 학생의 현재 학습 상태를 확인하고 수준에 맞는 수업 방향을 설계합니다. 영어와 수학의 개념 이해, 문제풀이, 오답 관리, 학습 습관까지 함께 점검해 꾸준히 실력이 쌓이도록 돕습니다.</p>
        <a class="center-button" href="{overview_href}">학원소개 보기</a>
      </div>
      <div class="center-about-points">
        <article>
          <strong>수준별 맞춤 수업</strong>
          <p>학생의 학년과 실력, 목표에 맞춰 필요한 개념과 문제 유형을 단계적으로 관리합니다.</p>
        </article>
        <article>
          <strong>영어·수학 전문 관리</strong>
          <p>주요 과목의 기초부터 심화까지 학습 흐름을 잡고 시험 대비까지 연결합니다.</p>
        </article>
        <article>
          <strong>학습 습관 코칭</strong>
          <p>숙제, 복습, 오답 정리를 꾸준히 확인해 스스로 공부하는 힘을 키웁니다.</p>
        </article>
      </div>
    </section>
"""


def remove_existing_about_summary(text: str) -> str:
    return re.sub(
        r'    <section class="center-section center-about-summary">.*?    </section>\n',
        "",
        text,
        flags=re.S,
    )


def update_region_page(page_file: Path) -> bool:
    text = page_file.read_text(encoding="utf-8", errors="ignore")
    updated = remove_existing_about_summary(text)
    summary = about_summary(page_file)
    if "  </main>" not in updated:
        return False
    updated = updated.replace("  </main>", summary + "  </main>", 1)
    if updated == text:
        return False
    page_file.write_text(updated, encoding="utf-8")
    return True


def update_district_page(page_file: Path) -> bool:
    text = page_file.read_text(encoding="utf-8", errors="ignore")
    updated = re.sub(
        r"<h1>([^<]*?)\s+와와학습코칭센터\s+영어수학\s+전문학원</h1>",
        r"<h1>\1 와와학습코칭센터</h1>",
        text,
        count=1,
    )
    updated = remove_existing_about_summary(updated)
    summary = about_summary(page_file)
    if "  </main>" not in updated:
        return False
    updated = updated.replace("  </main>", summary + "  </main>", 1)
    if updated == text:
        return False
    page_file.write_text(updated, encoding="utf-8")
    return True


def main():
    region_updated = 0
    district_updated = 0

    for page_file in sorted((ROOT / "center").glob("*/index.html")):
        if update_region_page(page_file):
            region_updated += 1

    for page_file in sorted((ROOT / "center").glob("*/*/index.html")):
        if update_district_page(page_file):
            district_updated += 1

    print(f"region_pages_updated={region_updated}")
    print(f"district_pages_updated={district_updated}")


if __name__ == "__main__":
    main()
