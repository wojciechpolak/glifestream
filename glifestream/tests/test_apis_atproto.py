import pytest
from unittest.mock import MagicMock, patch
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
