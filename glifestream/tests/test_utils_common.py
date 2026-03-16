from django.conf import settings
from glifestream.utils.common import get_theme


def test_get_theme_default():
    class MockRequest:
        COOKIES = {}

    request = MockRequest()
    # Should return the first theme from settings.THEMES
    assert get_theme(request) == settings.THEMES[0]


def test_get_theme_from_cookie():
    # Ensure there is more than one theme if possible or just test with what exists
    theme_name = settings.THEMES[0]

    class MockRequest:
        COOKIES = {'gls-theme': theme_name}

    request = MockRequest()
    assert get_theme(request) == theme_name


def test_get_theme_invalid_cookie():
    class MockRequest:
        COOKIES = {'gls-theme': 'non-existent-theme'}

    request = MockRequest()
    # Should fallback to default
    assert get_theme(request) == settings.THEMES[0]
