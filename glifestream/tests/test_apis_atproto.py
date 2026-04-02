import pytest
from unittest.mock import MagicMock, patch
from django.utils import timezone
from glifestream.apis.atproto import AtProtoService
from glifestream.stream.models import Entry


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
