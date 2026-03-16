import pytest
from unittest.mock import patch, MagicMock
from glifestream.apis.mastodon import MastodonService
from glifestream.stream.models import Entry


@pytest.fixture
def mastodon_json():
    return [
        {
            'id': '1',
            'created_at': '2023-11-01T12:00:00.000Z',
            'url': 'https://mastodon.social/@user/1',
            'content': '<p>Hello #world</p>',
            'uri': 'https://mastodon.social/users/user/statuses/1',
            'reblog': None,
            'account': {
                'display_name': 'Test User',
                'avatar_static': 'http://example.com/avatar.png',
            },
            'media_attachments': [],
        }
    ]


@pytest.mark.django_db
def test_mastodon_fetch_basic(service, mastodon_json):
    service.user_id = '123'
    service.save()

    with patch('glifestream.apis.mastodon.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = mastodon_json
        mock_get.return_value = mock_response

        with patch('glifestream.apis.mastodon.media.save_image') as mock_save:
            mock_save.return_value = 'thumb.png'

            api = MastodonService(service)
            api.run()

            e = Entry.objects.get(guid='https://mastodon.social/@user/1')
            assert e.author_name == 'Test User'
            assert 'Hello world' in e.title  # # is removed
            assert e.link_image == 'thumb.png'


@pytest.mark.django_db
def test_mastodon_reblog(service, mastodon_json):
    service.user_id = '123'
    service.save()

    reblog_data = mastodon_json[0].copy()
    reblog_data['reblog'] = {
        'id': '2',
        'created_at': '2023-11-01T11:00:00.000Z',
        'url': 'https://mastodon.social/@other/2',
        'content': '<p>Original post</p>',
        'account': {
            'display_name': 'Other User',
            'avatar_static': 'http://other.com/avatar.png',
        },
    }

    with patch('glifestream.apis.mastodon.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = [reblog_data]
        mock_get.return_value = mock_response

        api = MastodonService(service)
        api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@other/2')
        assert e.reblog is True
        assert e.reblog_by == 'Test User'


@pytest.mark.django_db
def test_mastodon_media(service, mastodon_json):
    service.user_id = '123'
    service.save()

    media_data = mastodon_json[0].copy()
    media_data['media_attachments'] = [
        {
            'type': 'image',
            'preview_url': 'http://img.com/prev.png',
            'url': 'http://img.com/large.png',
            'remote_url': 'http://remote.com/img.png',
            'meta': {'small': {'width': 100, 'height': 100}},
        }
    ]

    with patch('glifestream.apis.mastodon.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = [media_data]
        mock_get.return_value = mock_response

        api = MastodonService(service)
        api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@user/1')
        assert 'thumbnails' in e.content
        assert 'http://remote.com/img.png' in e.content


@pytest.mark.django_db
def test_mastodon_oauth2(service, mastodon_json):
    # Test fetch_oauth2 when user_id is empty
    service.user_id = ''
    service.save()

    with patch('glifestream.apis.mastodon.gls_oauth2.OAuth2Client') as mock_oauth:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mastodon_json
        mock_client.consumer.get.return_value = mock_response
        mock_oauth.return_value = mock_client

        api = MastodonService(service)
        api.run()

        assert Entry.objects.filter(guid='https://mastodon.social/@user/1').exists()
        service.refresh_from_db()
        assert service.last_checked is not None
