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


@patch('glifestream.filters.expand.media.save_image', return_value='thumb.jpg')
def test_videolinks_expands_a_link_to_its_own_video_address(_mock_save):
    url = 'https://www.youtube.com/watch?v=vid123'
    rendered = expand.videolinks(
        f'<div><a href="{url}" rel="noopener noreferrer nofollow" '
        f'target="_blank">{url}</a></div>'
    )

    assert rendered.startswith('<div><div data-id="youtube-vid123" class="play-video">')
    assert rendered.endswith('</div></div>')
    assert rendered.count('<a ') == 1


def test_videolinks_keeps_a_named_link_to_a_video():
    html = '<a href="https://www.youtube.com/watch?v=vid123">my video</a>'
    assert expand.videolinks(html) == html


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


def test_normalize_youtube_url_rejects_other_hosts_and_schemes():
    for url in (
        'ftp://youtu.be/vid123',
        'https://vimeo.com/123',
        'https://youtu.be/',
        'https://www.youtube.com/watch?v=bad id',
        'https://www.youtube-nocookie.com/v/vid123',
    ):
        assert expand.normalize_youtube_url(url) is None


def test_is_video_url():
    assert expand.is_video_url('https://youtu.be/vid123')
    assert expand.is_video_url('https://vimeo.com/42')
    assert not expand.is_video_url('https://vimeo.com/channels/staff')


def test_vimeo_thumbnail_url_prefers_the_large_size():
    with (
        patch('glifestream.filters.expand.httpclient.get'),
        patch(
            'glifestream.filters.expand.httpclient.require_json',
            return_value=[
                {'thumbnail_large': 'big.jpg', 'thumbnail_medium': 'mid.jpg'}
            ],
        ),
    ):
        assert expand.vimeo_thumbnail_url('123') == 'big.jpg'

    with (
        patch('glifestream.filters.expand.httpclient.get'),
        patch(
            'glifestream.filters.expand.httpclient.require_json',
            return_value=[{'thumbnail_medium': 'mid.jpg'}],
        ),
    ):
        assert expand.vimeo_thumbnail_url('123') == 'mid.jpg'

    with patch(
        'glifestream.filters.expand.httpclient.get', side_effect=Exception('down')
    ):
        assert expand.vimeo_thumbnail_url('123') is None


@patch('glifestream.filters.expand.media.save_image', return_value='thumb.jpg')
@patch(
    'glifestream.filters.expand.vimeo_thumbnail_url',
    return_value='https://i.vimeocdn.com/42.jpg',
)
def test_videolinks_renders_a_vimeo_card(_mock_thumb, _mock_save):
    rendered = expand.videolinks('see https://vimeo.com/42')

    assert rendered == (
        'see <div data-id="vimeo-42" class="play-video">'
        '<a href="https://vimeo.com/42" rel="nofollow">'
        '<img src="thumb.jpg" width="320" height="180" alt="Vimeo Video" /></a>'
        '<div class="playbutton"></div></div>'
    )


@patch('glifestream.filters.expand.vimeo_thumbnail_url', return_value=None)
def test_videolinks_leaves_vimeo_without_a_thumbnail(_mock_thumb):
    assert expand.videolinks('https://vimeo.com/42') == 'https://vimeo.com/42'


@patch('glifestream.filters.expand.vimeo_thumbnail_url')
def test_videolinks_leaves_vimeo_urls_inside_attributes(mock_thumb):
    html = '<a href="https://vimeo.com/42">clip</a>'
    assert expand.videolinks(html) == html
    mock_thumb.assert_not_called()


@patch('glifestream.filters.expand.oembed.discover')
def test_shortpics_embeds_a_flickr_photo(mock_discover):
    mock_discover.return_value = {
        'type': 'photo',
        'url': 'https://live.staticflickr.com/1.jpg',
    }

    rendered = expand.shortpics('https://www.flickr.com/photos/me/1')

    assert rendered == (
        '<p class="thumbnails"><a href="https://www.flickr.com/photos/me/1" '
        'rel="nofollow"><img src="https://live.staticflickr.com/1.jpg" '
        'alt="thumbnail" /></a></p>'
    )


@patch('glifestream.filters.expand.oembed.discover', return_value={'type': 'video'})
def test_shortpics_leaves_other_flickr_links(_mock_discover):
    url = 'https://www.flickr.com/photos/me/1'
    assert expand.shortpics(url) == url


def test_audiolinks_wraps_ogg_links():
    rendered = expand.audiolinks('<a href="https://example.com/song.ogg">Song</a>')

    assert rendered.startswith('<span data-id="audio-')
    assert rendered.endswith(
        ' class="play-audio"><a href="https://example.com/song.ogg">Song</a></span>'
    )


def test_maplinks_renders_coordinates():
    rendered = expand.maplinks('at http://maps.google.com/maps?ll=52.2297,21.0122 ok')

    assert rendered == (
        'at <div class="geo"><a href="http://maps.google.com/maps?ll=52.2297,21.0122"'
        ' class="map"><span class="latitude">52.2297000000</span> '
        '<span class="longitude">21.0122000000</span></a></div> ok'
    )


def test_maplinks_leaves_a_map_link_without_coordinates():
    url = 'http://maps.google.com/maps?q=Warsaw'
    assert expand.maplinks(url) == url
