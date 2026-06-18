import html
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path.cwd()
ZIP_PATH = Path(r"C:\Users\얼짱김종범\Desktop\홈페이지 새로할거 자료\A열_텍스트파일.zip")
OUT_DIR = ROOT / "generated_article_txt"
OUT_ZIP = ROOT / "generated_article_txt.zip"


def read_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949", "euc-kr", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def clean_source(value: str) -> str:
    value = re.sub(r"\[(?:html|HTML|짧은 소개 문단|우리 학원을 선택해야 하는 이유|수업 대상 학생.*?|과목별.*?|상담.*?|FAQ.*?)\]", " ", value)
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"</(?:p|h1|h2|h3|li|section|ul|ol)>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = value.replace("&#183;", "·")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def sort_key(name: str) -> int:
    match = re.search(r"A(\d+)", name)
    return int(match.group(1)) if match else 0


def extract_branch(text: str) -> str:
    match = re.search(r"와와학습코칭센터\s*([가-힣A-Za-z0-9]+점)", text)
    if match:
        return match.group(1)
    match = re.search(r"와와학습코칭센터\s*([가-힣A-Za-z0-9]+)", text)
    if match and len(match.group(1)) <= 8:
        return match.group(1)
    return ""


def extract_local(text: str, fallback_index: int) -> str:
    patterns = [
        r"([가-힣A-Za-z0-9·\s]+?)\s*고등학생학원",
        r"([가-힣A-Za-z0-9·\s]+?)\s*영어\s*수학\s*학원",
        r"([가-힣A-Za-z0-9·\s]+?)에서\s*(?:영어|수학|학원)",
        r"([가-힣A-Za-z0-9]+(?:동|읍|면|리|시|구|신도시|지구))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        candidate = match.group(1).strip()
        candidate = re.split(r"[,|:]", candidate)[-1].strip()
        candidate = candidate.split()[-1] if candidate.split() else candidate
        candidate = re.sub(r"^(?:추천|와와학습코칭센터|찾고|있다면)", "", candidate).strip()
        if 1 < len(candidate) <= 12 and "학원" not in candidate and "센터" not in candidate:
            return candidate

    branch = extract_branch(text)
    if branch.endswith("점"):
        return branch[:-1]
    return f"지역{fallback_index:04d}"


def has_high_focus(text: str) -> bool:
    return any(word in text for word in ("고등", "고1", "고2", "고3", "수능", "모의고사"))


def has_korean_subject(text: str) -> bool:
    return "국어" in text


def make_article(source: str, index: int) -> str:
    text = clean_source(source)
    local = extract_local(text, index)
    branch = extract_branch(text)
    branch_label = f"와와학습코칭센터 {branch}" if branch else f"{local} 와와학습코칭센터"
    title_center = f"{local} 와와학습코칭센터"
    area_label = local
    high_focus = has_high_focus(text)
    korean_subject = has_korean_subject(text)
    subject_text = "영어·수학·국어" if korean_subject else "영어·수학"
    exam_text = "내신·수능·모의고사" if high_focus else "내신과 학교 진도"

    return f"""<main class="article-main">
  <section class="article-hero">
    <p class="article-eyebrow">LOCAL ACADEMY GUIDE</p>
    <h1>{html.escape(title_center)} 영어·수학 학습 안내</h1>
  </section>

  <p class="article-intro">
    {html.escape(area_label)}에서 영어·수학 학원을 찾는 학생을 위해, 현재 실력 진단부터 개념 정리,
    문제풀이, 오답 관리까지 이어지는 학습 흐름을 안내합니다. {html.escape(branch_label)}은
    학생마다 다른 학습 속도와 목표를 확인해 {html.escape(exam_text)} 대비까지 자연스럽게 이어지도록 수업과 코칭을 함께 진행합니다.
  </p>

  <section class="article-section article-local-feature-section">
    <h2>{html.escape(local)} 수업의 핵심 포인트</h2>
    <div class="article-card-grid">
      <article class="article-card">
        <strong>학생별 학습 진단</strong>
        <p>처음부터 많은 문제만 풀기보다, 개념 이해도와 풀이 습관을 먼저 확인해 학생에게 필요한 학습 순서를 잡습니다.</p>
      </article>
      <article class="article-card">
        <strong>{html.escape(subject_text)} 균형 관리</strong>
        <p>{html.escape(subject_text)} 과목의 약점을 나누어 확인하고, 개념 정리와 유형 연습, 오답 관리가 이어지도록 학습 흐름을 잡습니다.</p>
      </article>
    </div>
  </section>

  <section class="article-section article-local-feature-section">
    <h2>선생님 특징</h2>
    <div class="article-card-grid">
      <article class="article-card">
        <strong>설명보다 이해를 우선합니다</strong>
        <p>학생이 어디에서 막히는지 질문과 풀이 과정을 통해 확인하고, 필요한 개념을 다시 연결해 줍니다.</p>
      </article>
      <article class="article-card">
        <strong>학습 태도까지 함께 봅니다</strong>
        <p>숙제, 복습, 오답 정리 습관을 꾸준히 점검해 수업 시간이 일회성으로 끝나지 않도록 관리합니다.</p>
      </article>
    </div>
  </section>

  <section class="article-section article-local-feature-section">
    <h2>수업 진행방식</h2>
    <div class="article-target-list">
      <article class="article-target-card">
        <h3>1. 현재 수준 확인</h3>
        <p>학생의 학년, 학교 진도, 최근 시험 흐름을 바탕으로 부족한 단원과 자주 틀리는 유형을 확인합니다.</p>
      </article>
      <article class="article-target-card">
        <h3>2. 개념 정리와 유형 학습</h3>
        <p>바로 문제풀이로 넘어가기보다 핵심 개념을 정리한 뒤, 대표 유형부터 응용 문제까지 단계적으로 연습합니다.</p>
      </article>
      <article class="article-target-card">
        <h3>3. 오답 관리와 학습 피드백</h3>
        <p>틀린 문제를 단순히 다시 푸는 데서 끝내지 않고, 왜 틀렸는지와 다음에 어떻게 풀어야 하는지를 정리합니다.</p>
      </article>
    </div>
  </section>

  <section class="article-section article-local-feature-section">
    <h2>학년별 학습 전략</h2>
    <div class="article-subject-grid">
      <article class="article-subject-card">
        <h3>초등</h3>
        <ul>
          <li>기초 연산, 어휘, 독해 습관을 안정적으로 잡습니다.</li>
          <li>중등 과정으로 이어질 핵심 개념을 부담 없이 준비합니다.</li>
        </ul>
      </article>
      <article class="article-subject-card">
        <h3>중등</h3>
        <ul>
          <li>학교 진도와 내신 대비를 함께 관리합니다.</li>
          <li>영어 문법과 수학 단원별 유형을 반복 점검합니다.</li>
        </ul>
      </article>
      <article class="article-subject-card">
        <h3>고등</h3>
        <ul>
          <li>내신과 수능형 문제풀이를 구분해 학습 전략을 세웁니다.</li>
          <li>약한 단원, 시간 관리, 오답 패턴을 집중적으로 관리합니다.</li>
        </ul>
      </article>
      <article class="article-subject-card">
        <h3>시험 대비</h3>
        <ul>
          <li>학교별 시험 범위와 출제 경향에 맞춰 복습 계획을 조정합니다.</li>
          <li>시험 전에는 실수 유형과 자주 틀리는 문제를 우선 점검합니다.</li>
        </ul>
      </article>
    </div>
  </section>

  <section class="article-closing">
    <p>
      {html.escape(title_center)}는 학생의 현재 상태를 기준으로 필요한 학습을 정리하고,
      상담을 통해 영어·수학 학습 방향을 자세히 안내드립니다.
    </p>
  </section>
</main>
"""


def main():
    OUT_DIR.mkdir(exist_ok=True)

    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = [name for name in zf.namelist() if name.endswith(".txt")]
        names.sort(key=sort_key)
        for idx, name in enumerate(names, start=1):
            source = read_text(zf.read(name))
            output = make_article(source, idx)
            (OUT_DIR / f"{idx:04d}.txt").write_text(output, encoding="utf-8")

    if OUT_ZIP.exists():
        OUT_ZIP.unlink()
    shutil.make_archive(str(OUT_ZIP.with_suffix("")), "zip", OUT_DIR)
    print(f"txt_files_created={len(list(OUT_DIR.glob('*.txt')))}")
    print(f"output_dir={OUT_DIR}")
    print(f"output_zip={OUT_ZIP}")


if __name__ == "__main__":
    main()
