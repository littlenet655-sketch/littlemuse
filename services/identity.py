import re
from safety.text_service import ADULT_TERMS
USERNAME_RE=re.compile(r'^[A-Za-z0-9_.]{3,30}$')
NAME_RE=re.compile(r"^[A-Za-z][A-Za-z .'-]{1,79}$")

def _contains_adult(value):
    low=(value or '').lower()
    return any(term in low for term in ADULT_TERMS)

def validate_username(value):
    value=(value or '').strip()
    return bool(USERNAME_RE.fullmatch(value)) and not _contains_adult(value)

def validate_name(value):
    value=' '.join((value or '').split())
    return bool(NAME_RE.fullmatch(value)) and not _contains_adult(value)
