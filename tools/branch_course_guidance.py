"""One reviewed course scope for visible summaries, FAQs and service schema.

The workbook's subjects are immutable source facts. Notes narrow publication
scope without declaring conflicting or unrecorded courses unavailable.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path


RULES_FILE = Path(__file__).parent / "data" / "branch-directory" / "course-guidance.json"
SUBJECTS = ("국어", "영어", "수학", "과학", "사회")
GRADES = tuple([f"초{i}" for i in range(1, 7)] + [f"중{i}" for i in range(1, 4)] + [f"고{i}" for i in range(1, 4)])
REGISTRATION_NOTE = "수업 요일과 시간표, 신규 등록 가능 여부는 상담에서 확인해 주세요."


@lru_cache(maxsize=1)
def rules_data() -> dict:
    data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    for name, rule in data["centers"].items():
        if not rule.get("sourceRow") or not rule.get("cells"):
            raise ValueError(f"수업 조건의 원본 행·셀 근거 누락: {name}")
        for subject, entry in rule.get("subjects", {}).items():
            if subject not in (*SUBJECTS, "*"):
                raise ValueError(f"수업 조건의 과목 오류: {name}/{subject}")
            if set(entry.get("hold", [])) - set((*GRADES, "*")):
                raise ValueError(f"수업 조건의 학년 오류: {name}/{subject}")
        notes = [*rule.get("notes", [])]
        for entry in rule.get("subjects", {}).values():
            notes.extend(entry.get("notes", []))
        for note in notes:
            if not note.get("text") or not note.get("levels") or set(note["levels"]) - set("초중고"):
                raise ValueError(f"수업 조건의 문구·학교급 오류: {name}")
    return data


def verify_source(workbook: Path) -> None:
    expected = rules_data()["sourceWorkbookSha256"]
    if hashlib.sha256(workbook.read_bytes()).hexdigest() != expected:
        raise ValueError("센터 원본 엑셀이 검토본과 다릅니다. 수업 조건을 다시 대조한 후 생성해 주세요.")


def center_rule(center: dict) -> dict:
    rule = rules_data()["centers"].get(center["routeName"], {})
    if rule and center.get("sourceRow") != rule["sourceRow"]:
        raise ValueError(f'센터 원본 행 불일치: {center["routeName"]}')
    return rule


def format_grades(grades: list[str] | tuple[str, ...]) -> str:
    invalid = set(grades) - set(GRADES)
    if invalid:
        raise ValueError(f"잘못된 학년: {sorted(invalid)}")
    indices = sorted({GRADES.index(grade) for grade in grades})
    runs: list[list[int]] = []
    for index in indices:
        if runs and index == runs[-1][-1] + 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    return " · ".join(GRADES[run[0]] if len(run) == 1 else f"{GRADES[run[0]]}~{GRADES[run[-1]]}" for run in runs)


def scoped_notes(notes: list[dict], prefix: str | None) -> list[str]:
    return list(dict.fromkeys(note["text"] for note in notes if prefix is None or prefix in note["levels"]))


def center_notes(center: dict, prefix: str | None = None) -> list[str]:
    return scoped_notes(center_rule(center).get("notes", []), prefix)


def course_guidance(center: dict, subject: str, prefix: str | None = None) -> dict:
    if subject not in SUBJECTS or prefix not in (None, "초", "중", "고"):
        raise ValueError(f"과목·학교급 오류: {subject}/{prefix}")
    original = center.get("subjects", {}).get(subject, [])
    format_grades(original)  # Do not silently accept a new/unrecognized source value.
    raw = [g for g in GRADES if g in original and (prefix is None or g.startswith(prefix))]
    rule = center_rule(center)
    entries = [rule.get("subjects", {}).get(key, {}) for key in ("*", subject)]
    hold = {g for entry in entries for g in entry.get("hold", [])}
    pending = [g for g in raw if g in hold or "*" in hold]
    grades = [g for g in raw if g not in pending]
    notes = []
    if pending:
        notes.append(f"{format_grades(pending)} {subject} 수업은 현재 개설 여부를 먼저 확인해 주세요.")
    notes.extend(scoped_notes([n for entry in entries for n in entry.get("notes", [])], prefix))
    return {
        "subject": subject, "rawGrades": raw, "grades": grades,
        "pendingGrades": pending, "notes": list(dict.fromkeys(notes)),
        "label": format_grades(grades) if grades else "개설 학년 문의",
    }


def course_answer(center: dict, subject: str, prefix: str) -> str:
    view = course_guidance(center, subject, prefix)
    level = {"초": "초등", "중": "중등", "고": "고등"}[prefix]
    if view["grades"]:
        lead = f'{center["displayName"]}의 {level} {subject} 안내 학년은 {view["label"]}입니다.'
    elif view["pendingGrades"]:
        lead = f'{center["displayName"]}의 {format_grades(view["pendingGrades"])} {subject} 수업은 현재 개설 여부를 먼저 확인해 주세요.'
    else:
        lead = f'{center["displayName"]}의 {level} {subject} 수업은 개설 학년과 진행 여부를 먼저 확인해 주세요.'
    # An all-pending range is already named in the lead; do not repeat it.
    notes = view["notes"][1:] if not view["grades"] and view["pendingGrades"] else view["notes"]
    return " ".join([lead, *notes, *center_notes(center, prefix), REGISTRATION_NOTE])


def branch_course_answer(center: dict) -> str:
    views = [course_guidance(center, subject) for subject in SUBJECTS]
    parts = [f'{v["subject"]} {v["label"]}' for v in views if v["rawGrades"] or v["notes"]]
    lead = "과목별 안내 범위는 " + ", ".join(parts) + "입니다." if parts else "과목별 개설 학년은 상담에서 확인해 주세요."
    notes = list(dict.fromkeys(n for v in views for n in v["notes"]))
    return " ".join([lead, *notes, *center_notes(center), REGISTRATION_NOTE])


def weekend_guidance(center: dict) -> str:
    return center_rule(center).get("weekend", center["weekend"])
