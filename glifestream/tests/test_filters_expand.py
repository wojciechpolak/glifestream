from unittest.mock import patch

from glifestream.filters import expand


@patch('glifestream.filters.expand.media.save_image', return_value='thumb.jpg')
def test_videolinks_supports_common_youtube_variants(_mock_save):
    cases = [
        'https://youtu.be/vid123',
        'https://youtu.be/vid123?si=sharetoken',
        'https://www.youtube.com/watch?v=vid123&t=90',
        'https://m.youtube.com/watch?v=vid123',
        'https://www.youtube.com/shorts/vid123',
        'https://www.youtube.com/live/vid123',
        'https://www.youtube.com/embed/vid123',
        'https://www.youtube-nocookie.com/embed/vid123',
    ]

    for url in cases:
        rendered = expand.videolinks(url)
        assert 'data-id="youtube-vid123"' in rendered
        assert 'href="https://www.youtube.com/watch?v=vid123"' in rendered
        assert 'thumb.jpg' in rendered


def test_videolinks_ignores_unsupported_youtube_urls():
    url = 'https://www.youtube.com/channel/not-a-video'
    assert expand.videolinks(url) == url


@patch('glifestream.filters.expand.media.save_image', return_value='thumb.jpg')
def test_videolinks_preserves_trailing_punctuation(_mock_save):
    rendered = expand.videolinks('Watch https://youtu.be/vid123.')
    assert 'data-id="youtube-vid123"' in rendered
    assert rendered.endswith('.')


def test_normalize_youtube_url_supports_common_variants():
    cases = [
        'https://youtu.be/vid123?si=sharetoken',
        'https://www.youtube.com/watch?v=vid123&t=90',
        'https://m.youtube.com/watch?v=vid123',
        'https://www.youtube.com/shorts/vid123',
        'https://www.youtube.com/live/vid123',
        'https://www.youtube.com/embed/vid123',
        'https://www.youtube-nocookie.com/embed/vid123',
    ]

    for url in cases:
        assert expand.normalize_youtube_url(url) == (
            'https://www.youtube.com/watch?v=vid123'
        )
