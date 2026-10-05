"""Command line: python -m notes.cli add "text" | list | find word."""
import sys

from notes.core import Notes


def main(argv, notes=None):
    notes = notes or Notes()
    cmd, *rest = argv or ["list"]
    if cmd == "add":
        return f"added {notes.add(' '.join(rest))}"
    if cmd == "find":
        return "\n".join(notes.find(rest[0] if rest else ""))
    return "\n".join(notes.all())


if __name__ == "__main__":
    print(main(sys.argv[1:]))
