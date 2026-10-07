"""Upgrading the players of videos in posts, and giving one another video."""

from __future__ import annotations

import itertools
import json
from unittest.mock import patch

import pytest

from glifestream import upgrades
from glifestream.filters import music, players
from glifestream.stream import media
from glifestream.stream.models import Entry, Service
from glifestream.utils import httpclient

POSTS = upgrades.UPGRADERS['post-videos']

OLD_THUMB = '[GLS-THUMBS]/aa48110be7944fd483b96f1e7310372310cbf556.jpg'
NEW_THUMB = '[GLS-THUMBS]/ad97b17ffccd1af56d7f1596ff2b47f4e6a487bf.webp'
OLD_PLAYER = (
    '<table class="vc"><tr><td><div data-id="youtube-2yOVITOeY0g" class="play-video">'
    '<a href="https://www.youtube.com/watch?v=2yOVITOeY0g" rel="nofollow">'
    '<img src="%s" width="200" height="150" alt="YouTube Video" /></a>'
    '<div class="playbutton"></div></div></td></tr></table>' % OLD_THUMB
)
TEXT = '<p>Nirvana - Aneurysm (guitar cover)</p>\n'
FLASH = (
    '{"content": [[{"url": "http://www.youtube.com/v/2yOVITOeY0g", '
    '"medium": "video", "type": "application/x-shockwave-flash"}]]}'
)

_guids = itertools.count(1)


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.APP_THUMBNAIL_FORMAT = 'WEBP'
    return tmp_path


def put_thumb(media_root, internal: str) -> None:
    name = internal.split('/', 1)[1]
    path = media_root / 'thumbs' / name[0] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'thumb')


@pytest.fixture
def videos(db):
    return Service.objects.create(
        name='Videos', api='selfposts', cls='videos', public=True
    )


def make_post(service, content, **fields) -> Entry:
    values = {
        'title': 'Nirvana - Aneurysm (guitar cover)',
        'link': 'http://example.org/stream/',
        'mblob': FLASH,
    }
    values.update(fields)
    return Entry.objects.create(
        service=service, guid='post-%d' % next(_guids), content=content, **values
    )


def current(vid='2yOVITOeY0g', src=NEW_THUMB, provider='youtube') -> str:
    return players.player_html(provider, vid, src)


def not_found(url: str) -> httpclient.FetchError:
    return httpclient.build_fetch_error(
        category='not_found',
        detail='HTTP 404',
        retryable=False,
        status_code=404,
        url=url,
    )


def test_an_old_player_is_legacy_and_a_current_one_is_not(videos, media_root):
    put_thumb(media_root, NEW_THUMB)
    old = make_post(videos, TEXT + OLD_PLAYER)
    fresh = make_post(
        videos,
        TEXT + current(),
        mblob=media.mrss_with_videos(None, TEXT + current()),
    )
    plain = make_post(videos, '<p>No video</p>', mblob=None)

    assert POSTS.is_legacy(old)
    assert not POSTS.is_legacy(fresh)
    assert not POSTS.is_legacy(plain)
    assert [e.pk for e in upgrades.pending(POSTS)] == [old.pk]


def test_the_player_of_a_music_card_is_the_cards_own(videos):
    card = music.card_html(
        music.Track('A', 'T', music.Cover(OLD_THUMB, 160, 160), 'abc')
    )
    entry = make_post(videos, card, mblob=None)

    assert not POSTS.is_legacy(entry)
    with pytest.raises(upgrades.Unavailable):
        POSTS.propose(entry)


def test_propose_fetches_a_thumbnail_and_keeps_the_text(videos):
    entry = make_post(videos, TEXT + OLD_PLAYER)

    with patch(
        'glifestream.filters.players.media.save_image', return_value=NEW_THUMB
    ) as save:
        proposal = POSTS.propose(entry)

    save.assert_called_once_with(
        'https://i.ytimg.com/vi/2yOVITOeY0g/mqdefault.jpg',
        downscale=True,
        size=(320, 180),
        strict=True,
    )
    assert proposal.content == TEXT + current()
    assert proposal.link == entry.link
    assert json.loads(proposal.mblob or '') == {
        'content': [
            [{'url': 'https://www.youtube.com/embed/2yOVITOeY0g', 'medium': 'video'}]
        ]
    }


def test_markup_only_when_the_thumbnail_is_current(videos, media_root):
    put_thumb(media_root, NEW_THUMB)
    stale = (TEXT + OLD_PLAYER).replace(OLD_THUMB, NEW_THUMB)
    stale = stale.replace('width="200" height="150"', 'width="320" height="180"')
    entry = make_post(videos, stale)

    with patch('glifestream.filters.players.media.save_image') as save:
        assert POSTS.propose(entry) == POSTS.propose_offline(entry)
    save.assert_not_called()
    assert upgrades.markup_only(POSTS) == [(entry, POSTS.propose_offline(entry))]


def test_a_gone_video_asks_for_another_copy(videos):
    entry = make_post(videos, TEXT + OLD_PLAYER)
    gone = not_found('https://i.ytimg.com/vi/2yOVITOeY0g/mqdefault.jpg')

    with patch('glifestream.filters.players.media.save_image', side_effect=gone):
        with pytest.raises(upgrades.Unavailable, match='another copy'):
            POSTS.propose(entry)


def test_the_owner_gives_another_video_of_either_provider(videos):
    entry = make_post(videos, TEXT + OLD_PLAYER + OLD_PLAYER.replace('2yOV', 'zzzz'))

    assert POSTS.guess(entry) == {
        'video': 'https://www.youtube.com/watch?v=2yOVITOeY0g'
    }
    assert [link.url for link in POSTS.field_help(entry, 'video', {})] == [
        'https://www.youtube.com/results?search_query='
        'Nirvana+-+Aneurysm+%28guitar+cover%29',
        'https://vimeo.com/search?q=Nirvana+-+Aneurysm+%28guitar+cover%29',
    ]
    with (
        patch(
            'glifestream.filters.players.oembed.discover',
            return_value={'thumbnail_url': 'https://i.vimeocdn.com/77.jpg'},
        ),
        patch('glifestream.filters.players.media.save_image', return_value=NEW_THUMB),
    ):
        proposal = POSTS.propose(entry, {'video': 'https://vimeo.com/77'})

    assert proposal.content == (
        TEXT + current('77', provider='vimeo') + current('zzzzITOeY0g')
    )
    with pytest.raises(upgrades.Unavailable, match='not a YouTube or Vimeo'):
        POSTS.propose(entry, {'video': 'https://example.com/77'})


def test_a_vimeo_video_without_a_thumbnail_is_gone(videos):
    entry = make_post(videos, OLD_PLAYER.replace('youtube-2yOVITOeY0g', 'vimeo-42'))

    with (
        patch('glifestream.filters.players.oembed.discover', return_value=None),
        pytest.raises(upgrades.Unavailable, match='Vimeo has no thumbnail'),
    ):
        POSTS.propose(entry)


def test_apply_keeps_the_dates_and_the_uploads_and_revert_restores(videos, media_root):
    upload = [{'url': '[GLS-UPLOAD]/x/p.jpg', 'medium': 'image'}]
    mblob = json.dumps({'content': json.loads(FLASH)['content'] + [upload]})
    entry = make_post(videos, TEXT + OLD_PLAYER, mblob=mblob)
    published = entry.date_published
    put_thumb(media_root, NEW_THUMB)

    with patch('glifestream.filters.players.media.save_image', return_value=NEW_THUMB):
        proposal = POSTS.propose(entry)
    upgrade = upgrades.apply(upgrades.make_token(entry, POSTS, proposal))

    entry.refresh_from_db()
    assert entry.content == TEXT + current()
    assert entry.date_published == published
    assert upload in json.loads(entry.mblob)['content']
    assert not POSTS.is_legacy(entry)

    upgrades.revert(upgrade.pk)
    entry.refresh_from_db()
    assert entry.content == TEXT + OLD_PLAYER
    assert entry.mblob == mblob
