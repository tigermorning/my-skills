import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from notes.cli import main  # noqa: E402
from notes.core import Notes  # noqa: E402


class NotesTest(unittest.TestCase):
    def test_add_and_list(self):
        n = Notes()
        n.add("buy milk")
        self.assertEqual(n.all(), ["buy milk"])

    def test_empty_is_rejected(self):
        with self.assertRaises(ValueError):
            Notes().add("  ")

    def test_find_ignores_case(self):
        n = Notes()
        n.add("Call Mom")
        self.assertEqual(n.find("mom"), ["Call Mom"])

    def test_cli_add(self):
        self.assertEqual(main(["add", "hi"], Notes()), "added 0")


if __name__ == "__main__":
    unittest.main()
