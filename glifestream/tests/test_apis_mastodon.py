import pytest
from unittest.mock import patch, MagicMock

from glifestream.apis.mastodon import MastodonService
from glifestream.stream.models import Entry
from glifestream.utils import httpclient


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


@pytest.mark.django_db
def test_mastodon_oauth2_fetch_error_propagates(service):
    service.user_id = ''
    service.save()

    with patch('glifestream.apis.mastodon.gls_oauth2.OAuth2Client') as mock_oauth:
        mock_client = MagicMock()
        mock_client.consumer.get.side_effect = httpclient.build_fetch_error(
            category='timeout',
            detail='Request to https://mastodon.social/api/v1/timelines/home?limit=40 timed out.',
            retryable=True,
            url='https://mastodon.social/api/v1/timelines/home?limit=40',
        )
        mock_oauth.return_value = mock_client

        api = MastodonService(service)
        with pytest.raises(httpclient.FetchError) as excinfo:
            api.run()

    assert excinfo.value.category == 'timeout'


@pytest.mark.django_db
def test_mastodon_renders_preview_card(service, mastodon_json):
    service.user_id = '123'
    service.save()

    card_data = mastodon_json[0].copy()
    card_data['card'] = {
        'url': 'https://example.com/story',
        'title': 'Example Story',
        'description': 'Preview card description',
        'image': 'https://example.com/story.png',
    }

    with patch('glifestream.apis.mastodon.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = [card_data]
        mock_get.return_value = mock_response

        api = MastodonService(service)
        api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@user/1')
        assert 'Example Story' in e.content
        assert 'Preview card description' in e.content
        assert 'href="https://example.com/story"' in e.content
        assert 'src="https://example.com/story.png"' in e.content


@pytest.mark.django_db
def test_mastodon_renders_inline_quoted_status(service, mastodon_json):
    service.user_id = '123'
    service.save()

    quote_data = mastodon_json[0].copy()
    quote_data['quote'] = {
        'state': 'accepted',
        'quoted_status': {
            'id': '2002',
            'url': 'https://mastodon.social/@quoted/2002',
            'content': '<p>Quoted body</p>',
            'account': {
                'display_name': 'Quoted User',
                'acct': 'quoted',
                'url': 'https://mastodon.social/@quoted',
            },
        },
    }
    quote_data['content'] = (
        '<p class="quote-inline">RE: <a href="https://mastodon.social/@quoted/2002">quoted</a></p>'
        '<p>Hello #world</p>'
    )

    with patch('glifestream.apis.mastodon.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = [quote_data]
        mock_get.return_value = mock_response

        api = MastodonService(service)
        api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@user/1')
        assert 'Quoted User' in e.content
        assert '<p>Quoted body</p>' in e.content
        assert 'quote-inline' not in e.content


@pytest.mark.django_db
def test_mastodon_hydrates_shallow_quoted_status(service, mastodon_json):
    service.user_id = '123'
    service.save()

    quote_data = mastodon_json[0].copy()
    quote_data['quote'] = {
        'state': 'accepted',
        'quoted_status_id': '2002',
    }

    list_response = MagicMock()
    list_response.json.return_value = [quote_data]
    status_response = MagicMock()
    status_response.status_code = 200
    status_response.json.return_value = {
        'id': '2002',
        'url': 'https://mastodon.social/@quoted/2002',
        'content': '<p>Hydrated quote body</p>',
        'account': {
            'display_name': 'Hydrated Quote',
            'acct': 'quoted',
            'url': 'https://mastodon.social/@quoted',
        },
    }

    with patch('glifestream.apis.mastodon.httpclient.get', side_effect=[list_response, status_response]) as mock_get:
        api = MastodonService(service)
        api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@user/1')
        assert 'Hydrated Quote' in e.content
        assert 'Hydrated quote body' in e.content
        assert mock_get.call_count == 2


@pytest.mark.django_db
def test_mastodon_renders_quote_placeholder_for_non_displayable_state(service, mastodon_json):
    service.user_id = '123'
    service.save()

    quote_data = mastodon_json[0].copy()
    quote_data['quote'] = {
        'state': 'pending',
        'quoted_status_id': '2002',
    }

    with patch('glifestream.apis.mastodon.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = [quote_data]
        mock_get.return_value = mock_response

        api = MastodonService(service)
        api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@user/1')
        assert 'Quoted post pending approval.' in e.content


@pytest.mark.django_db
def test_mastodon_hydrates_reply_parent(service, mastodon_json):
    service.user_id = '123'
    service.save()

    reply_data = mastodon_json[0].copy()
    reply_data['in_reply_to_id'] = '3003'

    list_response = MagicMock()
    list_response.json.return_value = [reply_data]
    status_response = MagicMock()
    status_response.status_code = 200
    status_response.json.return_value = {
        'id': '3003',
        'url': 'https://mastodon.social/@parent/3003',
        'content': '<p>Parent reply body</p>',
        'account': {
            'display_name': 'Reply Parent',
            'acct': 'parent',
            'url': 'https://mastodon.social/@parent',
        },
    }

    with patch('glifestream.apis.mastodon.httpclient.get', side_effect=[list_response, status_response]):
        api = MastodonService(service)
        api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@user/1')
        assert 'Replying to' in e.content
        assert 'Reply Parent' in e.content
        assert 'Parent reply body' in e.content
        assert e.content.index('Replying to') < e.content.index('Hello')
