from phone import format_phone

def test_mobile():
    assert format_phone("01012345678") == "010-1234-5678"

def test_mobile_with_spaces():
    assert format_phone("010 9876 5432") == "010-9876-5432"

def test_area_code():
    assert format_phone("0311234567") == "031-123-4567"

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all tests passed")
