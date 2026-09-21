"""Rewrite supplied subject manuscripts as useful, all-stage local hubs.

Only learning concerns are taken from manuscript examples. Center operation,
address, schools and course scope always come from the reviewed center data.
No simulated reviews, locality-wide student claims or promised outcomes.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

SOURCE = Path(r'C:\Users\1992k\Desktop\새 홈페이지 원고 작업용')

MATH_FOCUS = [
    ('함수', '식·표·그래프 연결'), ('부호', '계산 과정과 검산'),
    ('공식', '공식의 적용 조건'), ('확률', '경우 분류와 중복 점검'),
    ('보조선', '도형의 성질과 풀이 근거'), ('서술형', '서술형 풀이 기록'),
    ('문장제', '조건을 식으로 옮기기'), ('개념 간', '개념 사이의 연결'),
    ('변형 문제', '변형 조건 적용'), ('이전 학년', '이전 개념 복구'),
    ('난이도', '문제 난이도 배분'), ('범위', '시험 범위 우선순위'),
    ('단원별', '단원별 이해도 점검'), ('독립', '혼자 푸는 과정'),
    ('재현', '해설 없이 재풀이'), ('시간 제한', '시간 제한과 정확도'),
    ('속도', '문항별 시간 배분'), ('고난도', '기본·심화 시간 배분'),
    ('끝까지 읽기', '문제 조건 먼저 읽기'), ('오답 원인', '오답 원인 분류'),
    ('다시 풀지', '채점 다음 날 재확인'), ('시험 전날', '평일 누적 복습'),
    ('복습량', '복습 간격 설계'), ('노트', '복습할 수 있는 풀이 노트'),
    ('기록', '과정 중심 학습 기록'), ('질문', '학습 질문 정리'),
    ('새 단원', '새 단원의 시작점'), ('손을 놓', '기본과 응용의 연결'),
    ('여러 풀이', '풀이 방법 비교'), ('검산', '일관된 풀이 순서'),
    ('예제', '예제와 유사 문제 연결'), ('진도', '진도 뒤 이해도 확인'),
]

ENGLISH_PRACTICES = [
    ('선택지|요구 조건|근거', '독해 근거와 선택지 비교', '문제를 풀 때 정답을 고른 근거 문장과 다른 선택지를 제외한 이유를 한 줄씩 적어 보세요. 지문 요약과 문항 판단을 분리하면 해석이 맞는데 답을 틀리는 이유를 찾기 쉽습니다.'),
    ('서술형|어법|문법', '문장 구조와 직접 쓰기', '문장의 주어·동사와 수식어를 구분하고, 배운 어법을 사용해 짧은 문장을 직접 써 보세요. 용어를 아는 것과 문장 속에서 적용하는 것을 따로 확인하는 과정입니다.'),
    ('어휘|단어|암기', '어휘 기억과 문맥 적용', '외운 단어를 뜻만 다시 쓰지 말고 짧은 예문 안에서 사용해 보세요. 뜻이 떠오르지 않은 단어와 뜻은 알지만 문맥을 고르지 못한 단어를 따로 표시해 복습 범위를 나눕니다.'),
    ('긴 문장|문장 구조|해석', '끊어 읽기와 의미 연결', '지문에서 어려운 문장 한 개를 골라 의미 단위로 끊고 중심 내용을 말해 보세요. 해설을 덮은 뒤 연결어와 수식 범위를 다시 표시하면 실제 이해한 부분을 구분할 수 있습니다.'),
    ('시간|집중', '읽기 순서와 시간 배분', '같은 길이의 지문을 읽으며 처음 막힌 문장과 다시 읽은 부분을 표시해 보세요. 전체 속도를 재촉하기보다 어휘 확인·구문 해석·문항 판단 중 시간이 걸린 단계를 찾습니다.'),
    ('프린트|부교재|교과서', '학교 자료와 복습 연결', '교과서와 학교 프린트에서 같은 표현을 묶고, 설명을 이해한 부분과 직접 써 보기 어려운 부분을 나누어 보세요. 자료의 양보다 학교에서 배운 내용과 남은 질문을 연결하는 것이 먼저입니다.'),
    ('시험|수행평가|범위', '평가 일정과 공부 순서', '평가 일정과 학습 범위를 한 장에 적고 이미 설명할 수 있는 내용, 다시 읽을 내용, 질문할 내용으로 구분해 보세요. 수행평가 준비와 지필평가 복습이 겹치는 날의 분량부터 조정합니다.'),
    ('부담|자신감|미루', '부담을 줄이는 시작 분량', '지금 혼자 읽을 수 있는 짧은 문장부터 시작해 뜻을 말하고 한 문장을 바꾸어 써 보세요. 어려운 문제 수를 늘리기 전에 도움 없이 끝낸 과정을 기록하며 다음 분량을 정합니다.'),
    ('복습|오답|문제집|숙제', '복습 간격과 재확인', '학습을 마친 날에 남은 질문을 표시하고 다음 공부를 시작할 때 해설 없이 다시 풀어 보세요. 과제를 제출한 여부와 다시 설명할 수 있는 내용을 따로 기록하면 반복할 대상을 줄일 수 있습니다.'),
    ('혼자|유형|균형', '이해와 적용을 나누어 점검', '짧은 문장을 읽고 뜻을 설명한 뒤 조건이 달라진 문항을 혼자 풀어 보세요. 정답만 고치기보다 어떤 설명 뒤 해결했는지 기록하면 다음 수업에서 질문할 내용이 분명해집니다.'),
]


def section(text, label):
    match = re.search(rf'(?ms)^\[{re.escape(label)}\]\s*\n(.*?)(?=^\[[^\]]+\]\s*$|\Z)', text)
    return match[1].strip() if match else ''


def secondary_action(habit):
    choices = [
        ('문제집|기록|필기', '교재를 바꾸기 전 남은 질문을 한 곳에 모으고, 다음 학습에서 다시 확인한 날짜를 적습니다.'),
        ('질문|빈칸', '질문할 때는 마지막으로 이해한 부분과 처음 막힌 부분을 함께 표시합니다. 답을 받기 전에 시도한 방법도 한 줄 남겨 둡니다.'),
        ('힌트|해설|정답 암기|정답만', '설명이나 힌트를 받은 문제는 구분해 두고, 다음 날 도움 없이 한 번 더 시도합니다. 답이 아닌 판단 근거를 적는 것이 핵심입니다.'),
        ('시간|주말|집중|일정|단기간|계획', '등원일과 가정 학습일에 실제 사용할 수 있는 시간을 적어 봅니다. 필수 분량과 여유가 있을 때 할 분량을 나누어 하루에 몰리지 않게 합니다.'),
        ('보호자|혼자|관리', '학생이 먼저 완료한 내용과 남은 질문을 표시하고, 보호자는 그 기록을 함께 살펴보는 순서로 역할을 나눕니다.'),
        ('실패|싫어|미루|시도', '혼자 끝낼 수 있는 짧은 과제부터 시작하고, 어려워서 멈춘 지점은 질문으로 남겨 다음 학습의 시작점으로 사용합니다.'),
        ('선행|기본|단원|범위', '새 진도를 늘리기 전 현재 단원의 기본 확인 문제를 풀어 봅니다. 빠진 개념과 새로 공부할 내용을 같은 분량으로 묶지 않습니다.'),
    ]
    return next((value for pattern, value in choices if re.search(pattern, habit)), '공부를 마친 뒤 바로 이해한 내용과 다음 날 다시 설명할 내용을 구분해 기록합니다. 반복해서 막힌 항목은 다음 상담 질문으로 가져가세요.')


def parse_source(text, subject, file_name):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    title = section(text, '페이지타이틀')
    expected = f' {subject}학원'
    if not title.endswith(expected) or PurePosixPath(file_name).stem != title:
        raise ValueError(f'Manuscript name/title mismatch: {file_name}')
    locality = title[:-len(expected)]
    intro = section(text, '본문').split('## ')[0].strip()
    if subject == '수학':
        m = re.search(r'([^.!?\n]+?) 데다 (.*?) 습관이 있는 ((?:초등|중|고등)학교 [1-6]학년) 학생', intro)
        if not m:
            raise ValueError(f'Missing math situation: {title}')
        concern = m[1].strip().split('반 이름이 아니라 ')[-1].split('먼저 답하면, ')[-1]
        concern = re.sub(r'^특히\s+', '', concern).strip()
        habit = m[2]
        tail = intro[m.end():]
        practice = re.search(r'^(?:에게는 |이라면 |에게 필요한 답은 )(.+?연습)', tail)
        if not practice:
            practice = re.search(r'단계에서는 (.+?연습)', tail)
        if not practice:
            raise ValueError(f'Missing math practice: {title}')
        focus = next((label for key, label in MATH_FOCUS if key in concern), '풀이 과정과 복습 점검')
        action = f'{practice[1]}부터 시작해 보세요. 답을 맞혔는지와 별도로 처음 시도한 풀이, 설명 뒤 고친 풀이, 혼자 다시 해 본 풀이를 구분해 남깁니다.'
    else:
        m = re.search(r'이 페이지는 (.*?) 학생이면서 (.*?) 상황,', intro)
        if not m:
            raise ValueError(f'Missing English situation: {title}')
        concern = re.sub(r'\s+(?:초등 고학년|예비중1|예비고1|초[1-6]|중[1-3]|고[1-3]|초등부|중등부|고등부)$', '', m[1])
        # A source example sometimes paired a younger grade with high-school
        # language. The hub describes the learning concern, not that claim.
        concern = concern.replace('고등 내신에서 ', '학교 시험을 준비하며 ').replace('고등 영어로 넘어가며 ', '다음 학습 단계로 넘어가며 ').replace('초등 고학년 단계에서 ', '').replace('중학교 첫 시험을 앞두고 ', '첫 학교 시험을 앞두고 ')
        habit = m[2]
        focus, action = next(((label, value) for pattern, label, value in ENGLISH_PRACTICES if re.search(pattern, concern)), ('읽기·문장·복습 균형', '현재 교재에서 읽고 설명할 수 있는 문장과 다시 배울 문장을 구분해 보세요. 설명을 듣고 이해한 것과 혼자 적용한 것을 따로 기록합니다.'))
    if locality in concern or len(concern) > 75 or len(habit) > 90:
        raise ValueError(f'Unclean source concern: {title}/{concern}')
    return {'locality': locality, 'subject': subject, 'title': title, 'concern': concern,
            'habit': habit, 'focus': focus, 'practice': action, 'followup': secondary_action(habit),
            'sourceZip': f'{subject}학원.zip', 'sourceFile': file_name,
            'sourceSha256': hashlib.sha256(text.encode()).hexdigest()}


def load_sources():
    rows = []
    for subject in ('수학', '영어'):
        with zipfile.ZipFile(SOURCE / f'{subject}학원.zip') as archive:
            names = [n for n in archive.namelist() if n.lower().endswith('.txt')]
            if len(names) != 371:
                raise ValueError('Expected 371 manuscripts per subject')
            rows.extend(parse_source(archive.read(n).decode('utf-8-sig'), subject, n) for n in names)
    if len({(r['locality'], r['subject']) for r in rows}) != 742:
        raise ValueError('Duplicate/missing local subject manuscripts')
    return rows


def clean_schools(center, level):
    # Do not publish unresolved workbook candidates, cross-region notes or
    # abbreviations guessed into full names.
    return list(dict.fromkeys(n for n in center.get('schools', {}).get(level, [])
                             if n.endswith('학교') and not re.search(r'후보|확인|\[|\]|;', n)))[:5]


if __name__ == '__main__':
    rows = load_sources()
    print(json.dumps({'count': len(rows), 'samples': [r for r in rows if r['locality'] == '풍동']}, ensure_ascii=False, indent=2))
