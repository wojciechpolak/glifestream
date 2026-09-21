import pytest
from unittest.mock import patch, MagicMock

from glifestream.apis.youtube import YoutubeService
from glifestream.stream.models import Entry
from glifestream.utils import httpclient


@pytest.fixture
def youtube_json():
    return {
        'items': [
            {
                'id': 'item-1',
                'contentDetails': {'videoId': 'vid-123'},
                'snippet': {
                    'publishedAt': '2023-11-01T12:00:00Z',
                    'title': 'Test Video',
                    'channelTitle': 'Test Channel',
                    'thumbnails': {
                        'default': {
                            'url': 'http://img.com/def.png',
                            'width': 120,
                            'height': 90,
                        }
                    },
                },
            }
        ]
    }


@pytest.mark.django_db
def test_youtube_fetch_basic(service, youtube_json):
    service.url = 'MYKEY:PLAYLIST1'
    service.save()

    with patch('glifestream.apis.youtube.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = youtube_json
        mock_get.return_value = mock_response

        api = YoutubeService(service)
        api.run()

        e = Entry.objects.get(guid='tag:youtube.com,2008:video:vid-123')
        assert e.title == 'Test Video'
        assert e.author_name == 'Test Channel'
        assert 'vid-123' in e.content


@pytest.mark.django_db
def test_youtube_favorite(service, youtube_json):
    # Test favorite playlist kind
    service.url = 'MYKEY:PLAYLIST1#favorite'
    service.save()

    with patch('glifestream.apis.youtube.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = youtube_json
        mock_get.return_value = mock_response

        api = YoutubeService(service)
        api.run()

        e = Entry.objects.get(guid='tag:youtube.com,2008:favorite:item-1')
        assert e.title == 'Test Video'


@pytest.mark.django_db
def test_youtube_media_thumbs(service, youtube_json):
    service.url = 'MYKEY:PLAYLIST1'
    service.public = True  # Trigger save_image
    service.save()

    # Add medium thumb
    youtube_json['items'][0]['snippet']['thumbnails']['medium'] = {
        'url': 'http://img.com/med.png'
    }

    with patch('glifestream.apis.youtube.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = youtube_json
        mock_get.return_value = mock_response

        with patch('glifestream.apis.youtube.media.save_image') as mock_save:
            mock_save.return_value = 'local_med.png'

            api = YoutubeService(service)
            api.run()

            e = Entry.objects.get(guid='tag:youtube.com,2008:video:vid-123')
            assert 'local_med.png' in e.content
            assert 'width="320" height="180"' in e.content


@pytest.mark.django_db
def test_youtube_http_error(service):
    service.url = 'MYKEY:PLAYLIST1'
    service.save()

    with patch('glifestream.apis.youtube.httpclient.get') as mock_get:
        mock_get.side_effect = httpclient.build_fetch_error(
            category='auth',
            detail='HTTP 403 Forbidden from https://www.googleapis.com/youtube/v3/playlistItems',
            retryable=False,
            status_code=403,
            url='https://www.googleapis.com/youtube/v3/playlistItems',
        )

        api = YoutubeService(service, verbose=1)
        with pytest.raises(httpclient.FetchError) as excinfo:
            api.run()

    assert excinfo.value.category == 'auth'
    assert Entry.objects.count() == 0


def run_with(service, payload):
    with patch('glifestream.apis.youtube.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = payload
        mock_get.return_value = mock_response
        YoutubeService(service).run()
    return Entry.objects.get(guid='tag:youtube.com,2008:video:vid-123')


def test_parse_published_accepts_milliseconds():
    from glifestream.apis.youtube import _parse_published

    plain = _parse_published('2023-11-01T12:00:00Z')
    with_ms = _parse_published('2023-11-01T12:00:00.000Z')

    assert plain == with_ms
    assert plain.tzinfo is not None


@pytest.mark.parametrize(
    'available, expected',
    [
        (('default', 'high', 'medium'), ('medium.png', 320, 180)),
        (('default', 'high'), ('high.png', 200, 150)),
        (('default',), ('default.png', 200, 150)),
    ],
)
def test_pick_thumbnail_prefers_the_largest_listed(available, expected):
    from glifestream.apis.youtube import _pick_thumbnail

    thumbnails = {key: {'url': '%s.png' % key} for key in available}
    tn = _pick_thumbnail(thumbnails)

    assert tn is not None
    assert (tn['url'], tn['width'], tn['height']) == expected
    assert 'width' not in thumbnails[available[-1]]


def test_pick_thumbnail_needs_the_default_one():
    from glifestream.apis.youtube import _pick_thumbnail

    assert _pick_thumbnail({'medium': {'url': 'm.png'}}) is None
    assert _pick_thumbnail({}) is None


@pytest.mark.django_db
def test_youtube_without_thumbnails_links_the_video(service, youtube_json):
    service.url = 'MYKEY:PLAYLIST1'
    service.save()
    del youtube_json['items'][0]['snippet']['thumbnails']

    e = run_with(service, youtube_json)

    assert e.content == (
        '<a href="https://www.youtube.com/watch?v=vid-123">Test Video</a>'
    )


@pytest.mark.django_db
def test_youtube_skips_an_unchanged_video(service, youtube_json):
    service.url = 'MYKEY:PLAYLIST1'
    service.save()
    e = run_with(service, youtube_json)
    Entry.objects.filter(pk=e.pk).update(title='Edited locally')

    e = run_with(service, youtube_json)

    assert e.title == 'Edited locally'


def test_youtube_get_urls_passes_a_plain_url_through(service):
    service.url = 'https://example.com/feed.json'
    assert YoutubeService(service).get_urls() == ['https://example.com/feed.json']


def test_youtube_get_urls_without_a_key_has_nothing_to_fetch(service):
    service.url = 'no-playlists'
    assert YoutubeService(service).get_urls() == []
