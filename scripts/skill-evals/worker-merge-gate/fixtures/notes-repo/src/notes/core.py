"""Notes kept in memory: add, list, find."""


class Notes:
    def __init__(self):
        self.items = []

    def add(self, text):
        text = text.strip()
        if not text:
            raise ValueError("empty note")
        self.items.append(text)
        return len(self.items) - 1

    def all(self):
        return list(self.items)

    def find(self, word):
        return [t for t in self.items if word.lower() in t.lower()]
