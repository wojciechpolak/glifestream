import pytest
from unittest.mock import patch, MagicMock
from glifestream.apis.youtube import YoutubeService
from glifestream.stream.models import Entry


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
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.reason = 'Forbidden'
        mock_get.return_value = mock_response

        api = YoutubeService(service, verbose=1)
        api.run()

        assert Entry.objects.count() == 0
