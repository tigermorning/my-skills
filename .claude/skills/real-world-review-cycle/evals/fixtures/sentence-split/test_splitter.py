from splitter import split_sentences

def test_basic():
    assert split_sentences("안녕하세요. 반갑습니다!") == ["안녕하세요.", "반갑습니다!"]

def test_question():
    assert split_sentences("밥 먹었어? 응 먹었어.") == ["밥 먹었어?", "응 먹었어."]

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all tests passed")
