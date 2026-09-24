import re

def split_sentences(text: str) -> list[str]:
    """Split Korean/English mixed text into sentences."""
    parts = re.split(r'(?<=[.!?])\s*', text.strip())
    return [p.strip() for p in parts if p.strip()]
