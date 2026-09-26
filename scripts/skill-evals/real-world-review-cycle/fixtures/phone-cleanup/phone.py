import re

def format_phone(raw: str) -> str:
    """Normalize a Korean phone number to hyphenated form, e.g. 01012345678 -> 010-1234-5678."""
    digits = re.sub(r"\D", "", raw)
    return f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"
