import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from django.utils import timezone
from glifestream.apis.atproto import AtProtoService, filter_content
from glifestream.stream.models import Entry


def _make_facet(text, fragment, feature):
    text_bytes = text.encode('utf-8')
    fragment_bytes = fragment.encode('utf-8')
    start = text_bytes.index(fragment_bytes)
    end = start + len(fragment_bytes)
    return SimpleNamespace(
        index=SimpleNamespace(byte_start=start, byte_end=end),
        features=[feature],
    )


@pytest.mark.django_db
def test_atproto_process_entries(service):
    service.api = 'atproto'
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        # Mocking FeedViewPost structure
        mock_post = MagicMock()
        mock_post.cid = 'bafy-cid'
        mock_post.uri = 'at://did:plc:123/app.bsky.feed.post/456'
        mock_post.record.text = 'Hello Bluesky!'
        mock_post.record.created_at = '2025-01-01T12:00:00Z'
        mock_post.author.handle = 'user.bsky.social'
        mock_post.author.display_name = 'User'
        mock_post.author.avatar = None
        mock_post.embed = None

        mock_entry = MagicMock()
        mock_entry.post = mock_post

        api.process([mock_entry])

        # Check if Entry was created
        entry = Entry.objects.get(guid='bafy-cid')
        assert entry.title == 'Hello Bluesky!'
        assert 'Hello Bluesky!' in entry.content
        assert entry.author_name == 'User'


@pytest.mark.django_db
def test_atproto_process_marks_reposts_with_reposter_context(service):
    service.api = 'atproto'
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        mock_post = MagicMock()
        mock_post.cid = 'repost-cid'
        mock_post.uri = 'at://did:plc:original/app.bsky.feed.post/456'
        mock_post.record.text = 'Original author post'
        mock_post.record.created_at = '2025-01-01T12:00:00Z'
        mock_post.author.handle = 'original-author.bsky.social'
        mock_post.author.display_name = 'Original Author'
        mock_post.author.avatar = None
        mock_post.embed = None

        mock_entry = MagicMock()
        mock_entry.post = mock_post
        mock_entry.reason = SimpleNamespace(
            py_type='app.bsky.feed.defs#reasonRepost',
            indexed_at='2025-01-02T15:30:00Z',
            uri='at://did:plc:reposter/app.bsky.feed.repost/repost-123',
            by=SimpleNamespace(
                handle='reposter.bsky.social',
                display_name='Followed Reposter',
            ),
        )

        api.process([mock_entry])

        entry = Entry.objects.get(guid='repost-cid')
        assert entry.author_name == 'Original Author'
        assert entry.reblog is True
        assert entry.reblog_by == 'Followed Reposter'
        assert entry.reblog_uri == 'at://did:plc:reposter/app.bsky.feed.repost/repost-123'
        assert entry.date_published.isoformat() == '2025-01-02T15:30:00+00:00'
        assert filter_content(entry).startswith('Followed Reposter reblogged')


@pytest.mark.django_db
def test_atproto_process_skips_reposts_when_configured(service):
    service.api = 'atproto'
    service.skip_reblogs = True
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        mock_post = MagicMock()
        mock_post.cid = 'skipped-repost-cid'
        mock_post.uri = 'at://did:plc:original/app.bsky.feed.post/457'
        mock_post.record.text = 'Should be skipped'
        mock_post.record.created_at = '2025-01-01T12:00:00Z'
        mock_post.author.handle = 'original-author.bsky.social'
        mock_post.author.display_name = 'Original Author'
        mock_post.author.avatar = None
        mock_post.embed = None

        mock_entry = MagicMock()
        mock_entry.post = mock_post
        mock_entry.reason = SimpleNamespace(
            py_type='app.bsky.feed.defs#reasonRepost',
            indexed_at='2025-01-02T15:30:00Z',
            by=SimpleNamespace(
                handle='reposter.bsky.social',
                display_name='Followed Reposter',
            ),
        )

        api.process([mock_entry])

        assert Entry.objects.filter(guid='skipped-repost-cid').count() == 0


@pytest.mark.django_db
def test_atproto_process_renders_facets_and_mentions_tags(service):
    service.api = 'atproto'
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        text = 'Visit https://example.com by @alice\n#python'
        mock_post = MagicMock()
        mock_post.cid = 'facet-cid'
        mock_post.uri = 'at://did:plc:123/app.bsky.feed.post/789'
        mock_post.record.text = text
        mock_post.record.facets = [
            _make_facet(
                text,
                'https://example.com',
                SimpleNamespace(uri='https://example.com'),
            ),
            _make_facet(text, '@alice', SimpleNamespace(did='did:plc:alice')),
            _make_facet(text, '#python', SimpleNamespace(tag='python')),
        ]
        mock_post.record.created_at = '2025-01-01T12:00:00Z'
        mock_post.author.handle = 'user.bsky.social'
        mock_post.author.display_name = 'User'
        mock_post.author.avatar = None
        mock_post.embed = None

        mock_entry = MagicMock()
        mock_entry.post = mock_post

        api.process([mock_entry])

        entry = Entry.objects.get(guid='facet-cid')
        assert 'href="https://example.com"' in entry.content
        assert 'href="https://bsky.app/profile/did:plc:alice"' in entry.content
        assert '>@alice</a>' in entry.content
        assert 'href="https://bsky.app/hashtag/python"' in entry.content
        assert '>#python</a>' in entry.content
        assert '<br/>' in entry.content


@pytest.mark.django_db
@patch('glifestream.filters.expand.media.save_image', return_value='thumb.jpg')
def test_atproto_process_fallback_linkifies_plain_urls(_mock_save, service):
    service.api = 'atproto'
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        mock_post = MagicMock()
        mock_post.cid = 'plain-url-cid'
        mock_post.uri = 'at://did:plc:123/app.bsky.feed.post/457'
        mock_post.record.text = 'Hello\nhttps://youtu.be/vid123?si=sharetoken'
        mock_post.record.facets = None
        mock_post.record.created_at = '2025-01-01T12:00:00Z'
        mock_post.author.handle = 'user.bsky.social'
        mock_post.author.display_name = 'User'
        mock_post.author.avatar = None
        mock_post.embed = None

        mock_entry = MagicMock()
        mock_entry.post = mock_post

        api.process([mock_entry])

        entry = Entry.objects.get(guid='plain-url-cid')
        assert '<br/>' in entry.content
        assert 'href="https://youtu.be/vid123?si=sharetoken"' in entry.content
        assert 'data-id="youtube-vid123"' in entry.content
        assert 'href="https://www.youtube.com/watch?v=vid123"' in entry.content


@pytest.mark.django_db
@patch('glifestream.filters.expand.media.save_image', return_value='thumb.jpg')
def test_atproto_process_external_embed_supports_youtube_shortlinks(
    _mock_save, service
):
    service.api = 'atproto'
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        mock_post = MagicMock()
        mock_post.cid = 'embed-cid'
        mock_post.uri = 'at://did:plc:123/app.bsky.feed.post/458'
        mock_post.record.text = 'External video'
        mock_post.record.facets = None
        mock_post.record.created_at = '2025-01-01T12:00:00Z'
        mock_post.author.handle = 'user.bsky.social'
        mock_post.author.display_name = 'User'
        mock_post.author.avatar = None
        mock_post.embed = SimpleNamespace(
            external=SimpleNamespace(uri='https://youtu.be/vid123?si=sharetoken')
        )

        mock_entry = MagicMock()
        mock_entry.post = mock_post

        api.process([mock_entry])

        entry = Entry.objects.get(guid='embed-cid')
        assert 'data-id="youtube-vid123"' in entry.content
        assert 'href="https://www.youtube.com/watch?v=vid123"' in entry.content


@pytest.mark.django_db
def test_atproto_run_logs_in_and_fetches_home_timeline(service):
    service.api = 'atproto'
    service.creds = 'playwright.test:app-pass'
    service.save()

    mock_client = MagicMock()
    mock_client.get_timeline.return_value.feed = []

    with patch('glifestream.apis.atproto.Client', return_value=mock_client):
        api = AtProtoService(service)
        with patch.object(api, 'process') as mock_process:
            api.run()

    mock_client.login.assert_called_once_with('playwright.test', 'app-pass')
    mock_client.get_timeline.assert_called_once_with(limit=None)
    mock_client.get_author_feed.assert_not_called()
    mock_process.assert_called_once_with([])
    service.refresh_from_db()
    assert service.last_checked is not None


@pytest.mark.django_db
def test_atproto_run_uses_author_feed_when_user_id_is_present(service):
    service.api = 'atproto'
    service.creds = 'playwright.test:app-pass'
    service.user_id = 'author-feed'
    service.last_checked = timezone.now()
    service.save()

    mock_client = MagicMock()
    mock_client.me = MagicMock(did='did:plc:testdid')
    mock_client.get_author_feed.return_value.feed = []

    with patch('glifestream.apis.atproto.Client', return_value=mock_client):
        api = AtProtoService(service)
        with patch.object(api, 'process') as mock_process:
            api.run()

    mock_client.login.assert_called_once_with('playwright.test', 'app-pass')
    mock_client.get_author_feed.assert_called_once_with(
        'did:plc:testdid', filter='posts_no_replies', limit=50
    )
    mock_client.get_timeline.assert_not_called()
    mock_process.assert_called_once_with([])


@pytest.mark.django_db
def test_atproto_run_swallows_login_errors(service):
    service.api = 'atproto'
    service.creds = 'playwright.test:app-pass'
    service.save()

    mock_client = MagicMock()
    mock_client.login.side_effect = Exception('boom')

    with patch('glifestream.apis.atproto.Client', return_value=mock_client):
        api = AtProtoService(service)
        with patch.object(api, 'process') as mock_process:
            api.run()

    mock_client.login.assert_called_once_with('playwright.test', 'app-pass')
    mock_client.get_timeline.assert_not_called()
    mock_client.get_author_feed.assert_not_called()
    mock_process.assert_not_called()
    service.refresh_from_db()
    assert service.last_checked is None
