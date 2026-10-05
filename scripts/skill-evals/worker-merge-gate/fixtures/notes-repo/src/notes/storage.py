"""Save and load notes as one line per note."""
from pathlib import Path


def save(notes, path):
    Path(path).write_text("\n".join(notes.all()) + "\n", encoding="utf-8")


def load(notes, path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            notes.add(line)
    return notes
