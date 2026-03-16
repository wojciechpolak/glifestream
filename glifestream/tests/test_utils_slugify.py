# -*- coding: utf-8 -*-
from glifestream.utils.slugify import slugify


def test_slugify_basic():
    assert slugify('Hello World') == 'hello-world'
    assert slugify('Hello World', do_slugify=False) == 'Hello World'


def test_slugify_special_chars():
    # Test Greek
    assert slugify('ΑΒΓ') == 'abg'
    # Test Cyrillic
    assert slugify('АБВ') == 'abv'
    # Test Polish/Latin extended
    assert slugify('Zażółć gęślą jań') == 'zazolc-gesla-jan'


def test_slugify_overwrite_map():
    # Overwrite '!' to 'X' (it's not in the map by default, but matched by regex)
    assert slugify('!!!', overwrite_char_map={'!': 'X'}) == 'xxx'


def test_slugify_strip_unknown():
    # Use characters that are definitely not in the map and not used in other tests
    # to avoid side-effect issues from global __char_map updates in slugify()
    assert slugify('Hello$%^') == 'hello'
