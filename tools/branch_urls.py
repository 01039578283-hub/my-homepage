"""Canonical branch > neighborhood subject > school-stage URL contract."""
from urllib.parse import quote

DOMAIN = 'https://wawa-center.kr'
LEVELS = ('초등', '중등', '고등')
SUBJECTS = ('수학', '영어')


def segment(value):
    if not isinstance(value, str) or not value or value != value.strip() or any(x in value for x in '/\\%?#\x00\r\n') or value in ('.', '..'):
        raise ValueError(f'Unsafe URL segment: {value!r}')
    return value


def center_path(center):
    return f'/지점안내/{segment(center["region"])}/{segment(center["routeName"])}/'


def hub_path(center, locality, subject):
    if subject not in SUBJECTS or locality not in center['neighborhoods']:
        raise ValueError((locality, subject))
    return center_path(center) + f'{segment(locality)}{subject}학원/'


def course_path(center, locality, level, subject):
    if level not in LEVELS:
        raise ValueError(level)
    return hub_path(center, locality, subject) + level + '/'


def legacy_path(center, locality, level, subject):
    return center_path(center) + f'{segment(locality)}{level}{subject}학원/'


def canonical(path):
    return DOMAIN + quote(path, safe='/#')


def crumbs(center, locality, subject, level=None):
    rows = [('홈', '/'), ('지점안내', '/지점안내/'),
            (center['region'], f'/지점안내/{center["region"]}/'),
            (center['routeName'], center_path(center)),
            (f'{locality} {subject}학원', hub_path(center, locality, subject))]
    if level:
        rows.append((f'{level} {subject}', course_path(center, locality, level, subject)))
    return rows
