import json
import pytest
from unittest.mock import patch, MagicMock

from glifestream.apis.mastodon import MastodonService, _render_status_reference
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
def test_mastodon_video_attachment_renders_player_and_exports_mrss(
    service, mastodon_json
):
    service.user_id = '123'
    service.save()

    media_data = mastodon_json[0].copy()
    media_data['media_attachments'] = [
        {
            'id': 'video-1',
            'type': 'gifv',
            'preview_url': 'https://files.example.com/video-thumb.png',
            'url': 'https://files.example.com/video.mp4',
            'description': 'Shader breakpoints',
            'meta': {'original': {'width': 1280, 'height': 976}},
        }
    ]

    with patch('glifestream.apis.mastodon.httpclient.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = [media_data]
        mock_get.return_value = mock_response

        with patch(
            'glifestream.apis.mastodon.media.save_image',
            side_effect=lambda url, **kwargs: url,
        ):
            api = MastodonService(service)
            api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@user/1')
        assert 'class="play-video"' in e.content
        assert 'data-id="mastodon-video-1"' in e.content
        assert 'data-src="https://files.example.com/video.mp4"' in e.content
        assert 'data-poster="https://files.example.com/video-thumb.png"' in e.content
        assert 'data-media-type="gifv"' in e.content
        assert 'data-width="1280" data-height="976"' in e.content
        assert 'alt="Shader breakpoints"' in e.content
        assert e.mblob is not None

        mblob = json.loads(e.mblob)
        assert mblob['content'][0][0] == {
            'url': 'https://files.example.com/video.mp4',
            'medium': 'video',
            'type': 'video/mp4',
            'isdefault': 'true',
        }


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

    with patch(
        'glifestream.apis.mastodon.httpclient.get',
        side_effect=[list_response, status_response],
    ) as mock_get:
        api = MastodonService(service)
        api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@user/1')
        assert 'Hydrated Quote' in e.content
        assert 'Hydrated quote body' in e.content
        assert mock_get.call_count == 2


@pytest.mark.django_db
def test_mastodon_renders_quote_placeholder_for_non_displayable_state(
    service, mastodon_json
):
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

    with patch(
        'glifestream.apis.mastodon.httpclient.get',
        side_effect=[list_response, status_response],
    ):
        api = MastodonService(service)
        api.run()

        e = Entry.objects.get(guid='https://mastodon.social/@user/1')
        assert 'Replying to' in e.content
        assert 'Reply Parent' in e.content
        assert 'Parent reply body' in e.content
        assert e.content.index('Replying to') < e.content.index('Hello')


def test_status_reference_quotes_the_author_and_body():
    html = _render_status_reference(
        {
            'account': {'display_name': 'Alice', 'url': 'https://m.example/@alice'},
            'content': '<p>Original</p>',
        },
        label='Quoted post',
    )

    assert 'mastodon-reference' in html
    assert 'Quoted post' in html
    assert 'href="https://m.example/@alice"' in html
    assert '>Alice<' in html
    assert '<p>Original</p>' in html


def test_status_reference_falls_back_to_acct_then_the_status_url():
    html = _render_status_reference(
        {'account': {'acct': 'bob@m.example'}, 'url': 'https://m.example/@bob/9'},
        label='Replying to',
    )

    assert 'href="https://m.example/@bob/9"' in html
    assert 'bob@m.example' in html


def test_status_reference_shows_the_link_itself_when_there_is_no_name():
    html = _render_status_reference(
        {'account': {'url': 'https://m.example/@carol'}, 'content': '<p>Hi</p>'},
        label='Quoted post',
    )

    assert html.count('https://m.example/@carol') == 2


def test_status_reference_uses_a_hash_when_nothing_links_anywhere():
    html = _render_status_reference({'content': '<p>Hi</p>'}, label='Quoted post')

    assert 'href="#"' in html


def test_status_reference_escapes_a_plain_text_status():
    html = _render_status_reference(
        {'account': {'display_name': 'Dave'}, 'text': 'tea & <biscuits>'},
        label='Quoted post',
    )

    assert '<p>tea &amp; &lt;biscuits&gt;</p>' in html


def test_status_reference_says_so_when_there_is_no_text_at_all():
    html = _render_status_reference(
        {'account': {'display_name': 'Eve'}, 'text': ''}, label='Quoted post'
    )

    assert 'No text content.' in html


def test_status_reference_escapes_the_author_name_and_link():
    html = _render_status_reference(
        {
            'account': {
                'display_name': 'Mallory & "friends"',
                'url': 'https://m.example/?a=1&b=2',
            },
            'content': '<p>x</p>',
        },
        label='Quoted post',
    )

    assert 'Mallory &amp; &quot;friends&quot;' in html
    assert 'https://m.example/?a=1&amp;b=2' in html


def test_render_video_attachment_full():
    from glifestream.apis.mastodon import _render_video_attachment

    attachment = {
        'id': '7',
        'type': 'gifv',
        'url': 'https://m.example/v.mp4',
        'preview_url': 'https://m.example/p.jpg',
        'description': 'A <cat>',
        'meta': {'original': {'width': 640, 'height': 360}},
    }
    with patch(
        'glifestream.apis.mastodon.media.save_image', return_value='[GLS-THUMBS]/p'
    ) as save:
        html = _render_video_attachment(attachment, is_public=True)

    save.assert_called_once_with('https://m.example/p.jpg')
    assert html == (
        ' <div data-id="mastodon-7" data-src="https://m.example/v.mp4"'
        ' data-poster="[GLS-THUMBS]/p" data-media-type="gifv"'
        ' data-width="640" data-height="360" class="play-video">'
        '<a href="https://m.example/v.mp4" rel="nofollow">'
        '<img src="[GLS-THUMBS]/p" alt="A &lt;cat&gt;" /></a>'
        '<div class="playbutton"></div></div>'
    )


def test_render_video_attachment_minimal():
    from glifestream.apis.mastodon import _render_video_attachment

    with patch('glifestream.apis.mastodon.media.save_image') as save:
        html = _render_video_attachment(
            {'url': 'https://m.example/v.mp4', 'meta': {'original': {'width': 'x'}}},
            is_public=True,
        )

    save.assert_not_called()
    assert html == (
        ' <div data-id="mastodon-https://m.example/v.mp4"'
        ' data-src="https://m.example/v.mp4" class="play-video">'
        '<a href="https://m.example/v.mp4" rel="nofollow">video attachment</a>'
        '<div class="playbutton"></div></div>'
    )
    assert _render_video_attachment({'url': ''}, is_public=False) == ''


def test_render_video_attachment_private_keeps_the_remote_poster():
    from glifestream.apis.mastodon import _render_video_attachment

    with patch('glifestream.apis.mastodon.media.save_image') as save:
        html = _render_video_attachment(
            {
                'url': 'https://m.example/v.mp4',
                'preview_url': 'https://m.example/p.jpg',
            },
            is_public=False,
        )

    save.assert_not_called()
    assert 'data-poster="https://m.example/p.jpg"' in html


def test_render_card():
    from glifestream.apis.mastodon import _render_card

    card = {
        'url': 'https://news.example/a',
        'title': 'Big & news',
        'description': 'Details',
        'image': 'https://news.example/a.jpg',
    }
    with patch(
        'glifestream.apis.mastodon.media.save_image', return_value='[GLS-THUMBS]/a'
    ):
        html = _render_card(card, is_public=True)

    assert html == (
        ' <blockquote class="mastodon-card mastodon-preview">'
        '<p><a href="https://news.example/a" rel="nofollow">Big &amp; news</a></p>'
        '<p>Details</p>'
        '<p class="thumbnails"><a href="https://news.example/a" rel="nofollow">'
        '<img src="[GLS-THUMBS]/a" alt="Big &amp; news" /></a></p>'
        '</blockquote>'
    )


def test_render_card_minimal_and_missing():
    from glifestream.apis.mastodon import _render_card

    assert _render_card({'url': 'https://news.example/a'}, is_public=False) == (
        ' <blockquote class="mastodon-card mastodon-preview">'
        '<p><a href="https://news.example/a" rel="nofollow">https://news.example/a</a></p>'
        '</blockquote>'
    )
    assert _render_card(None, is_public=False) == ''
    assert _render_card({'title': 'no url'}, is_public=False) == ''
