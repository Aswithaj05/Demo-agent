from app.string_utils import slugify, truncate


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"


def test_slugify_strips_edges():
    assert slugify("  --Already--Slugged--  ") == "already-slugged"


def test_truncate_short():
    assert truncate("hi", 10) == "hi"


def test_truncate_long():
    assert truncate("hello world", 8) == "hello..."
