import pytest
import json
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from typing import cast
from django.utils import timezone
from glifestream.apis.atproto import AtProtoService, filter_content
from atproto_client.models.app.bsky.feed.defs import FeedViewPost
from glifestream.stream.models import Entry
from glifestream.stream import media


def _make_facet(text, fragment, feature):
    text_bytes = text.encode('utf-8')
    fragment_bytes = fragment.encode('utf-8')
    start = text_bytes.index(fragment_bytes)
    end = start + len(fragment_bytes)
    return SimpleNamespace(
        index=SimpleNamespace(byte_start=start, byte_end=end),
        features=[feature],
    )


def _make_post(
    cid: str,
    text: str,
    *,
    created_at: str = '2025-01-01T12:00:00Z',
    embed=None,
    record_embed=None,
):
    return SimpleNamespace(
        cid=cid,
        uri=f'at://did:plc:123/app.bsky.feed.post/{cid}',
        record=SimpleNamespace(
            text=text,
            facets=None,
            created_at=created_at,
            embed=record_embed,
        ),
        author=SimpleNamespace(
            handle='user.bsky.social',
            display_name='User',
            avatar=None,
        ),
        embed=embed,
    )


def _make_feed_view_post(post, *, reason=None) -> FeedViewPost:
    return cast(FeedViewPost, SimpleNamespace(post=post, reason=reason))


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
def test_atproto_process_renders_native_video_embed_and_exports_mrss(service):
    service.api = 'atproto'
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        mock_post = _make_post(
            'native-video-cid',
            'Native video',
            embed=SimpleNamespace(
                py_type='app.bsky.embed.video#view',
                playlist='https://video.bsky.app/watch/example/playlist.m3u8',
                thumbnail='https://video.bsky.app/watch/example/thumbnail.jpg',
                alt=None,
                aspect_ratio=None,
            ),
            record_embed=SimpleNamespace(
                py_type='app.bsky.embed.video',
                video=SimpleNamespace(ref='blob'),
                alt='Trackside clip',
                aspect_ratio=SimpleNamespace(width=3840, height=2160),
            ),
        )
        mock_entry = _make_feed_view_post(mock_post)

        api.process([mock_entry])

        entry = Entry.objects.get(guid='native-video-cid')
        assert 'class="play-video"' in entry.content
        assert 'data-id="atproto-native-video-cid"' in entry.content
        assert (
            'data-playlist="https://video.bsky.app/watch/example/playlist.m3u8"'
            in entry.content
        )
        assert (
            'data-poster="https://video.bsky.app/watch/example/thumbnail.jpg"'
            in entry.content
        )
        assert 'data-width="3840" data-height="2160"' in entry.content
        assert (
            '<a href="https://bsky.app/profile/user.bsky.social/post/native-video-cid"'
            in entry.content
        )
        assert 'src="https://video.bsky.app/watch/example/thumbnail.jpg"' in entry.content
        assert 'width="3840" height="2160"' not in entry.content
        assert 'alt="Trackside clip"' in entry.content
        assert '<div class="playbutton"></div>' in entry.content

        assert entry.mblob is not None
        mblob = json.loads(entry.mblob)
        assert mblob['content'][0][0] == {
            'url': 'https://video.bsky.app/watch/example/playlist.m3u8',
            'medium': 'video',
            'type': 'application/x-mpegURL',
            'isdefault': 'true',
        }

        xml = media.mrss_gen_xml(entry)
        assert 'application/x-mpegURL' in xml
        assert 'isDefault="true"' in xml


@pytest.mark.django_db
def test_atproto_process_supports_record_with_media_video_embed(service):
    service.api = 'atproto'
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        mock_post = _make_post(
            'record-with-media-cid',
            'Video with attached record',
            embed=SimpleNamespace(
                py_type='app.bsky.embed.recordWithMedia#view',
                media=SimpleNamespace(
                    py_type='app.bsky.embed.video#view',
                    playlist='https://video.bsky.app/watch/example/nested.m3u8',
                    thumbnail='https://video.bsky.app/watch/example/nested.jpg',
                    alt='Nested video thumbnail',
                    aspect_ratio=SimpleNamespace(width=1280, height=720),
                )
            ),
        )
        mock_entry = _make_feed_view_post(mock_post)

        api.process([mock_entry])

        entry = Entry.objects.get(guid='record-with-media-cid')
        assert 'class="play-video"' in entry.content
        assert 'data-id="atproto-record-with-media-cid"' in entry.content
        assert 'data-playlist="https://video.bsky.app/watch/example/nested.m3u8"' in entry.content
        assert 'data-width="1280" data-height="720"' in entry.content
        assert 'src="https://video.bsky.app/watch/example/nested.jpg"' in entry.content
        assert 'alt="Nested video thumbnail"' in entry.content
        assert 'width="1280" height="720"' not in entry.content
        assert entry.mblob is not None
        assert 'https://video.bsky.app/watch/example/nested.m3u8' in entry.mblob


@pytest.mark.django_db
def test_atproto_process_native_video_embed_tolerates_missing_optional_fields(service):
    service.api = 'atproto'
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        mock_post = _make_post(
            'video-no-optional-cid',
            'Video without optional metadata',
            embed=SimpleNamespace(
                py_type='app.bsky.embed.video#view',
                playlist='https://video.bsky.app/watch/example/no-optional.m3u8',
                thumbnail='https://video.bsky.app/watch/example/no-optional.jpg',
            ),
        )
        mock_entry = _make_feed_view_post(mock_post)

        api.process([mock_entry])

        entry = Entry.objects.get(guid='video-no-optional-cid')
        assert 'class="play-video"' in entry.content
        assert 'data-id="atproto-video-no-optional-cid"' in entry.content
        assert 'src="https://video.bsky.app/watch/example/no-optional.jpg"' in entry.content
        assert 'alt="video thumbnail"' in entry.content
        assert 'data-width=' not in entry.content
        assert ' width=' not in entry.content
        assert entry.mblob is not None


@pytest.mark.django_db
def test_atproto_process_image_embed_still_renders_thumbnails(service):
    service.api = 'atproto'
    service.save()

    with patch('glifestream.apis.atproto.Client'):
        api = AtProtoService(service)

        mock_post = _make_post(
            'image-embed-cid',
            'Image embed',
            embed=SimpleNamespace(
                images=[
                    SimpleNamespace(
                        thumb='https://cdn.bsky.app/thumb.jpg',
                        fullsize='https://cdn.bsky.app/full.jpg',
                        aspect_ratio=SimpleNamespace(width=640, height=480),
                    )
                ]
            ),
        )
        mock_entry = _make_feed_view_post(mock_post)

        api.process([mock_entry])

        entry = Entry.objects.get(guid='image-embed-cid')
        assert 'src="https://cdn.bsky.app/thumb.jpg"' in entry.content
        assert 'data-imgurl="https://cdn.bsky.app/full.jpg"' in entry.content
        assert 'width="640" height="480"' in entry.content
        assert 'class="play-video"' not in entry.content
        assert entry.mblob is None


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
