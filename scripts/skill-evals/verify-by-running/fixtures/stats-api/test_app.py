from app import mean_of


def test_mean():
    assert mean_of("1,2,3") == 2.0


def test_single():
    assert mean_of("5") == 5.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all tests passed")
