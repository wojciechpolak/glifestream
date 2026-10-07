"""Upgrading old video entries to their provider's current markup."""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock, patch

import pytest
from django.core import signing

from glifestream import upgrades
from glifestream.apis import vimeo, youtube
from glifestream.stream.models import Entry, EntryUpgrade, Media, Service
from glifestream.upgrades.types import Link, find_player
from glifestream.utils import httpclient

YT = upgrades.UPGRADERS['youtube']
VIMEO = upgrades.UPGRADERS['vimeo']

OLD_THUMB = '[GLS-THUMBS]/afa533f8755176f7934c687ecdd8ea0450969d88.jpg'
NEW_THUMB = '[GLS-THUMBS]/ad97b17ffccd1af56d7f1596ff2b47f4e6a487bf.webp'
NEWER_THUMB = '[GLS-THUMBS]/0b710d898c38bc79547e9c1b98ce5dc40f94587b.webp'
FLASH_MBLOB = (
    '{"content": [[{"url": "http://www.youtube.com/v/abc", "medium": "video"}]]}'
)

_guids = itertools.count(1)


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.APP_THUMBNAIL_FORMAT = 'WEBP'
    return tmp_path


def put_thumb(media_root, internal: str) -> None:
    """Write the file behind a [GLS-THUMBS] reference."""
    name = internal.split('/', 1)[1]
    path = media_root / 'thumbs' / name[0] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'thumb')


@pytest.fixture
def yt_service(db):
    return Service.objects.create(name='YouTube', api='youtube', public=True)


@pytest.fixture
def vimeo_service(db):
    return Service.objects.create(name='Vimeo', api='vimeo', public=True)


def make_entry(service, content, **fields) -> Entry:
    values = {
        'title': 'A Video',
        'link': 'https://www.youtube.com/watch?v=abc',
        'mblob': None,
    }
    values.update(fields)
    return Entry.objects.create(
        service=service, guid='guid-%d' % next(_guids), content=content, **values
    )


def yt_current(vid='abc', src=NEW_THUMB) -> str:
    return youtube.player_html(vid, youtube.video_link(vid), src, 320, 180)


# The shapes old YouTube entries were stored in, all of them legacy.
YT_LEGACY = [
    '<table class="vc"><tr><td><div id="youtube-abc" class="play-video"><a href="https://www.youtube.com/watch?v=abc" rel="nofollow"><img src="%s" width="200" height="150" alt="YouTube Video" /></a><div class="playbutton"></div></div></td></tr></table>'
    % OLD_THUMB,
    '<p><table class="vc"><tr><td><div data-id="youtube-abc" class="play-video"><a href="https://www.youtube.com/watch?v=abc" rel="nofollow"><img src="%s" width="200" height="150" alt="YouTube Video" /></a><div class="playbutton"></div></div></td></tr></table></p>'
    % OLD_THUMB,
    '<table class="vc"><tr><td><div id="youtube-abc" class="play-video"><a href="https://www.youtube.com/watch?v=abc" rel="nofollow"><img src="%s" width="320" height="180" alt="YouTube Video" /></a><div class="playbutton"></div></div></td></tr></table>'
    % OLD_THUMB,
    '<table class="vc"><tr><td><div class="play-video" id="youtube-abc"><a href="https://www.youtube.com/watch?v=abc" rel="nofollow"><img alt="YouTube Video" height="150" src="%s" width="200"/></a><div class="playbutton"></div></div></td></tr></table>'
    % OLD_THUMB,
    # What imports stored until the id became a data-id.
    '<div id="youtube-abc" class="play-video"><a href="https://www.youtube.com/watch?v=abc" rel="nofollow"><img src="%s" width="320" height="180" alt="YouTube Video" /></a><div class="playbutton"></div></div>'
    % NEW_THUMB,
]


# ------------------------------------------------------------------ parsing


def test_find_player_reads_either_id_and_any_attribute_order():
    for content in YT_LEGACY:
        player = find_player(content, 'youtube')
        assert player is not None
        assert player.video_id == 'abc'
        assert player.src in (OLD_THUMB, NEW_THUMB)


def test_find_player_ignores_other_providers_and_plain_links():
    assert find_player(YT_LEGACY[0], 'vimeo') is None
    assert (
        find_player('<a href="https://youtu.be/x">Deleted video</a>', 'youtube') is None
    )


# ----------------------------------------------------------------- is_legacy


@pytest.mark.parametrize('content', YT_LEGACY)
def test_old_youtube_shapes_are_legacy(yt_service, media_root, content):
    put_thumb(media_root, NEW_THUMB)
    put_thumb(media_root, OLD_THUMB)

    assert YT.is_legacy(make_entry(yt_service, content))


def test_a_fresh_youtube_import_is_not_legacy(yt_service, media_root):
    put_thumb(media_root, NEW_THUMB)

    assert not YT.is_legacy(make_entry(yt_service, yt_current()))


def test_a_plain_link_is_not_legacy(yt_service):
    entry = make_entry(yt_service, '<a href="https://youtu.be/abc">Deleted video</a>')

    assert not YT.is_legacy(entry)


@pytest.mark.parametrize(
    'fields',
    [
        {'link': 'http://www.youtube.com/watch?v=abc'},
        {'mblob': FLASH_MBLOB},
        {'mblob': '{"content": [""]}'},
    ],
)
def test_a_stale_link_or_media_is_legacy(yt_service, media_root, fields):
    put_thumb(media_root, NEW_THUMB)

    assert YT.is_legacy(make_entry(yt_service, yt_current(), **fields))


def test_a_missing_thumbnail_file_is_legacy(yt_service):
    assert YT.is_legacy(make_entry(yt_service, yt_current()))


def test_a_change_to_the_renderer_makes_current_entries_legacy(
    yt_service, media_root, monkeypatch
):
    """The next renderer change needs no new upgrader."""
    put_thumb(media_root, NEW_THUMB)
    entry = make_entry(yt_service, yt_current())
    assert not YT.is_legacy(entry)

    original = youtube.player_html
    monkeypatch.setattr(
        youtube,
        'player_html',
        lambda *a: original(*a).replace('class="play-video"', 'class="play-video v2"'),
    )

    assert YT.is_legacy(entry)


def test_a_private_service_keeps_remote_thumbnails_current(db):
    service = Service.objects.create(name='YT', api='youtube', public=False)
    src = youtube.THUMBNAIL_URL % ('abc', 'mqdefault')

    assert not YT.is_legacy(make_entry(service, yt_current(src=src)))


def test_a_fresh_vimeo_import_is_not_legacy(vimeo_service, media_root):
    put_thumb(media_root, NEW_THUMB)
    entry = make_entry(
        vimeo_service,
        vimeo.player_html('42', 'https://vimeo.com/42', 'A & B', NEW_THUMB),
        title='A & B',
        link='https://vimeo.com/42',
        mblob=vimeo.player_mblob('42'),
    )

    assert not VIMEO.is_legacy(entry)


def test_an_unescaped_vimeo_alt_is_legacy(vimeo_service, media_root):
    put_thumb(media_root, NEW_THUMB)
    content = vimeo.player_html('42', 'https://vimeo.com/42', 'A', NEW_THUMB).replace(
        'alt="A"', 'alt=""A" by B"'
    )
    entry = make_entry(
        vimeo_service,
        content,
        title='"A" by B',
        link='https://vimeo.com/42',
        mblob=vimeo.player_mblob('42'),
    )

    assert VIMEO.is_legacy(entry)


# ------------------------------------------------------------------- propose


def test_propose_keeps_a_current_thumbnail_without_fetching(yt_service, media_root):
    put_thumb(media_root, NEW_THUMB)
    entry = make_entry(yt_service, YT_LEGACY[-1], mblob=FLASH_MBLOB)

    with patch('glifestream.apis.youtube.media.save_image') as save_image:
        proposal = YT.propose(entry)

    save_image.assert_not_called()
    assert proposal == upgrades.Proposal(
        content=yt_current(), link='https://www.youtube.com/watch?v=abc', mblob=None
    )


def test_propose_fetches_what_a_fresh_import_would(yt_service):
    entry = make_entry(
        yt_service, YT_LEGACY[0], link='http://www.youtube.com/watch?v=abc'
    )

    with patch(
        'glifestream.apis.youtube.media.save_image', return_value=NEWER_THUMB
    ) as save_image:
        proposal = YT.propose(entry)
        fresh = youtube.render_player(
            'abc', youtube.video_link('abc'), youtube.thumbnails_of('abc'), public=True
        )

    assert proposal.content == fresh == yt_current(src=NEWER_THUMB)
    assert proposal.link == 'https://www.youtube.com/watch?v=abc'
    # The upgrade asks for the reason a download fails; the import does not.
    for strict in (True, False):
        save_image.assert_any_call(
            'https://i.ytimg.com/vi/abc/mqdefault.jpg',
            downscale=True,
            size=(320, 180),
            strict=strict,
        )


def not_found(url: str) -> httpclient.FetchError:
    return httpclient.build_fetch_error(
        category='not_found',
        detail='HTTP 404 from %s' % url,
        retryable=False,
        status_code=404,
        url=url,
    )


def test_propose_reports_a_video_youtube_no_longer_has(yt_service):
    entry = make_entry(yt_service, YT_LEGACY[0])

    with (
        patch(
            'glifestream.apis.youtube.media.save_image',
            side_effect=not_found('https://i.ytimg.com/vi/abc/mqdefault.jpg'),
        ),
        pytest.raises(upgrades.Unavailable, match='YouTube has no thumbnail'),
    ):
        YT.propose(entry)


def test_propose_reports_a_thumbnail_it_cannot_save(yt_service, caplog):
    entry = make_entry(yt_service, YT_LEGACY[0])
    denied = PermissionError(13, 'Permission denied', '/media/thumbs/a/ad97.webp')

    with patch('glifestream.apis.youtube.media.save_image', side_effect=denied):
        with pytest.raises(upgrades.Unavailable) as raised:
            YT.propose(entry)

    message = str(raised.value)
    assert message.startswith('The thumbnail could not be saved:')
    assert 'Permission denied' in message and '/media/thumbs/a/ad97.webp' in message
    assert 'deleted' not in message
    assert 'Permission denied' in caplog.text


def test_propose_checks_the_remote_thumbnail_of_a_private_service(db):
    service = Service.objects.create(name='YT', api='youtube', public=False)
    entry = make_entry(service, YT_LEGACY[0])

    with patch(
        'glifestream.upgrades.types.httpclient.head',
        side_effect=httpclient.build_fetch_error(
            category='not_found',
            detail='HTTP 404',
            retryable=False,
            status_code=404,
            url='https://i.ytimg.com/vi/abc/mqdefault.jpg',
        ),
    ):
        with pytest.raises(upgrades.Unavailable):
            YT.propose(entry)

    with patch(
        'glifestream.upgrades.types.httpclient.head',
        return_value=MagicMock(status_code=200),
    ):
        proposal = YT.propose(entry)

    assert 'src="https://i.ytimg.com/vi/abc/mqdefault.jpg"' in proposal.content


def test_propose_asks_vimeo_oembed_for_the_thumbnail(vimeo_service):
    entry = make_entry(
        vimeo_service,
        YT_LEGACY[0].replace('youtube-abc', 'vimeo-42'),
        title='A Clip',
        link='https://vimeo.com/42',
    )

    with (
        patch(
            'glifestream.upgrades.videos.oembed.discover',
            return_value={'thumbnail_url': 'https://i.vimeocdn.com/42_640'},
        ) as discover,
        patch(
            'glifestream.apis.vimeo.media.save_image', return_value=NEWER_THUMB
        ) as save_image,
    ):
        proposal = VIMEO.propose(entry)

    discover.assert_called_once_with('https://vimeo.com/42', 'vimeo', maxwidth=640)
    save_image.assert_called_once_with(
        'https://i.vimeocdn.com/42_640', downscale=True, size=(320, 180), strict=True
    )
    assert proposal == upgrades.Proposal(
        content=vimeo.player_html('42', 'https://vimeo.com/42', 'A Clip', NEWER_THUMB),
        link='https://vimeo.com/42',
        mblob=vimeo.player_mblob('42'),
    )


def test_propose_reports_a_video_vimeo_no_longer_has(vimeo_service):
    entry = make_entry(vimeo_service, YT_LEGACY[0].replace('youtube-abc', 'vimeo-42'))

    with (
        patch('glifestream.upgrades.videos.oembed.discover', return_value=None),
        pytest.raises(upgrades.Unavailable, match='Vimeo'),
    ):
        VIMEO.propose(entry)


def test_the_video_field_starts_from_the_video_shown(yt_service, vimeo_service):
    yt = make_entry(yt_service, YT_LEGACY[0], title='Budgie&#39;s <b>Parents</b>')
    vm = make_entry(vimeo_service, YT_LEGACY[0].replace('youtube-abc', 'vimeo-42'))

    assert YT.guess(yt) == {'video': 'https://www.youtube.com/watch?v=abc'}
    assert VIMEO.guess(vm) == {'video': 'https://vimeo.com/42'}
    assert YT.field_help(yt, 'video', {}) == [
        Link(
            'Search YouTube',
            'https://www.youtube.com/results?search_query=Budgie%27s+Parents',
        ),
        Link('Search Vimeo', 'https://vimeo.com/search?q=Budgie%27s+Parents'),
    ]
    assert VIMEO.field_help(vm, 'video', {}) == [
        Link('Search Vimeo', 'https://vimeo.com/search?q=A+Video'),
        Link('Search YouTube', 'https://www.youtube.com/results?search_query=A+Video'),
    ]


def test_propose_plays_another_copy_the_owner_entered(yt_service, media_root):
    # The thumbnail of the old video is current; that of the copy is fetched.
    put_thumb(media_root, NEW_THUMB)
    entry = make_entry(yt_service, YT_LEGACY[-1].replace(OLD_THUMB, NEW_THUMB))

    with patch(
        'glifestream.apis.youtube.media.save_image', return_value=NEWER_THUMB
    ) as save_image:
        proposal = YT.propose(entry, {'video': 'https://youtu.be/copy1'})

    save_image.assert_called_once_with(
        'https://i.ytimg.com/vi/copy1/mqdefault.jpg',
        downscale=True,
        size=(320, 180),
        strict=True,
    )
    assert proposal == upgrades.Proposal(
        content=yt_current('copy1', NEWER_THUMB),
        link='https://www.youtube.com/watch?v=copy1',
        mblob=None,
    )


@pytest.mark.parametrize('video', ['', 'https://www.youtube.com/watch?v=abc'])
def test_propose_with_the_same_video_is_the_usual_upgrade(
    yt_service, media_root, video
):
    put_thumb(media_root, NEW_THUMB)
    entry = make_entry(yt_service, YT_LEGACY[-1])

    with patch('glifestream.apis.youtube.media.save_image') as save_image:
        proposal = YT.propose(entry, {'video': video})

    save_image.assert_not_called()
    assert proposal == YT.propose(entry)


def test_propose_refuses_what_is_no_video_address(yt_service, vimeo_service):
    yt = make_entry(yt_service, YT_LEGACY[0])
    vm = make_entry(vimeo_service, YT_LEGACY[0].replace('youtube-abc', 'vimeo-42'))

    for upgrader, entry in ((YT, yt), (VIMEO, vm)):
        with pytest.raises(upgrades.Unavailable, match='not a YouTube or Vimeo'):
            upgrader.propose(entry, {'video': 'https://example.com/42'})


def test_propose_plays_a_youtube_copy_of_a_video_gone_from_vimeo(vimeo_service):
    entry = make_entry(
        vimeo_service,
        YT_LEGACY[0].replace('youtube-abc', 'vimeo-42'),
        title='A Clip',
        link='https://vimeo.com/42',
    )

    with (
        patch(
            'glifestream.upgrades.videos.oembed.discover', side_effect=AssertionError
        ),
        patch(
            'glifestream.apis.youtube.media.save_image', return_value=NEWER_THUMB
        ) as save_image,
    ):
        proposal = VIMEO.propose(entry, {'video': 'https://youtu.be/copy1'})

    save_image.assert_called_once_with(
        'https://i.ytimg.com/vi/copy1/mqdefault.jpg',
        downscale=True,
        size=(320, 180),
        strict=True,
    )
    assert proposal == upgrades.Proposal(
        content=yt_current('copy1', NEWER_THUMB),
        link='https://www.youtube.com/watch?v=copy1',
        mblob=None,
    )


def test_propose_plays_a_vimeo_copy_of_a_video_gone_from_youtube(yt_service):
    entry = make_entry(yt_service, YT_LEGACY[0], title='A Clip')

    with (
        patch(
            'glifestream.upgrades.videos.oembed.discover',
            return_value={'thumbnail_url': 'https://i.vimeocdn.com/77_640'},
        ) as discover,
        patch('glifestream.apis.vimeo.media.save_image', return_value=NEWER_THUMB),
    ):
        proposal = YT.propose(entry, {'video': 'https://vimeo.com/77'})

    discover.assert_called_once_with('https://vimeo.com/77', 'vimeo', maxwidth=640)
    assert proposal == upgrades.Proposal(
        content=vimeo.player_html('77', 'https://vimeo.com/77', 'A Clip', NEWER_THUMB),
        link='https://vimeo.com/77',
        mblob=vimeo.player_mblob('77'),
    )


def test_propose_plays_another_vimeo_copy(vimeo_service):
    entry = make_entry(
        vimeo_service,
        YT_LEGACY[0].replace('youtube-abc', 'vimeo-42'),
        title='A Clip',
        link='https://vimeo.com/42',
    )

    with (
        patch(
            'glifestream.upgrades.videos.oembed.discover',
            return_value={'thumbnail_url': 'https://i.vimeocdn.com/77_640'},
        ) as discover,
        patch('glifestream.apis.vimeo.media.save_image', return_value=NEWER_THUMB),
    ):
        proposal = VIMEO.propose(entry, {'video': 'https://vimeo.com/77'})

    discover.assert_called_once_with('https://vimeo.com/77', 'vimeo', maxwidth=640)
    assert proposal == upgrades.Proposal(
        content=vimeo.player_html('77', 'https://vimeo.com/77', 'A Clip', NEWER_THUMB),
        link='https://vimeo.com/77',
        mblob=vimeo.player_mblob('77'),
    )


# --------------------------------------------------------------------- queue


def test_pending_lists_legacy_entries_oldest_first_without_skipped(
    yt_service, media_root
):
    put_thumb(media_root, NEW_THUMB)
    newer = make_entry(yt_service, YT_LEGACY[0])
    older = make_entry(yt_service, YT_LEGACY[1])
    Entry.objects.filter(pk=older.pk).update(date_published='2007-01-01T00:00:00Z')
    make_entry(yt_service, yt_current())
    skipped = make_entry(yt_service, YT_LEGACY[2])
    upgrades.skip(skipped, YT)

    assert [e.pk for e in upgrades.pending(YT)] == [older.pk, newer.pk]
    assert upgrades.counts(YT) == {
        'pending': 2,
        'markup_only': 0,
        'applied': 0,
        'skipped': 1,
    }

    assert upgrades.requeue_skipped(YT) == 1
    assert skipped.pk in [e.pk for e in upgrades.pending(YT)]


# --------------------------------------------------------------------- apply


def approve(entry, upgrader, media_root, src=NEW_THUMB, values=None) -> str:
    put_thumb(media_root, src)
    with patch('glifestream.apis.youtube.media.save_image', return_value=src):
        with patch('glifestream.apis.vimeo.media.save_image', return_value=src):
            with patch(
                'glifestream.upgrades.videos.oembed.discover',
                return_value={'thumbnail_url': 'https://i.vimeocdn.com/x'},
            ):
                proposal = upgrader.propose(entry, values)
    return upgrades.make_token(entry, upgrader, proposal)


def test_apply_stores_the_approved_proposal_and_keeps_a_backup(yt_service, media_root):
    entry = make_entry(
        yt_service,
        YT_LEGACY[0],
        link='http://www.youtube.com/watch?v=abc',
        mblob=FLASH_MBLOB,
    )
    token = approve(entry, YT, media_root)

    with patch('glifestream.stream.models.page_cache.invalidate') as invalidate:
        upgrade = upgrades.apply(token)

    entry.refresh_from_db()
    assert entry.content == yt_current()
    assert entry.link == 'https://www.youtube.com/watch?v=abc'
    assert entry.mblob is None
    assert not YT.is_legacy(entry)
    invalidate.assert_called()
    assert upgrade.status == EntryUpgrade.STATUS_APPLIED
    assert (upgrade.old_content, upgrade.old_link, upgrade.old_mblob) == (
        YT_LEGACY[0],
        'http://www.youtube.com/watch?v=abc',
        FLASH_MBLOB,
    )
    assert upgrade.new_content == entry.content
    # YouTube imports never register their thumbnail.
    assert not Media.objects.filter(entry=entry).exists()


def test_apply_refuses_an_entry_changed_after_its_preview(yt_service, media_root):
    entry = make_entry(yt_service, YT_LEGACY[0])
    token = approve(entry, YT, media_root)
    Entry.objects.filter(pk=entry.pk).update(content=YT_LEGACY[0] + ' edited')

    with pytest.raises(upgrades.UpgradeConflict, match='changed'):
        upgrades.apply(token)

    entry.refresh_from_db()
    assert entry.content == YT_LEGACY[0] + ' edited'
    assert not EntryUpgrade.objects.exists()


def test_apply_refuses_a_forged_token(yt_service, media_root):
    entry = make_entry(yt_service, YT_LEGACY[0])
    token = approve(entry, YT, media_root)
    data = signing.loads(token, salt='glifestream.upgrades')
    data['c'] = '<script>alert(1)</script>'
    forged = signing.dumps(data, salt='not the salt', compress=True)

    with pytest.raises(upgrades.UpgradeConflict):
        upgrades.apply(forged)
    with pytest.raises(upgrades.UpgradeConflict):
        upgrades.apply(token[:-2] + 'xx')

    entry.refresh_from_db()
    assert entry.content == YT_LEGACY[0]


def test_apply_refuses_a_thumbnail_gone_since_the_preview(yt_service, media_root):
    entry = make_entry(yt_service, YT_LEGACY[0])
    token = approve(entry, YT, media_root, src=NEWER_THUMB)
    name = NEWER_THUMB.split('/', 1)[1]
    (media_root / 'thumbs' / name[0] / name).unlink()

    with pytest.raises(upgrades.UpgradeConflict, match='thumbnail'):
        upgrades.apply(token)

    entry.refresh_from_db()
    assert entry.content == YT_LEGACY[0]


def test_apply_registers_the_thumbnail_of_a_vimeo_upload_only(
    vimeo_service, media_root
):
    old = YT_LEGACY[0].replace('youtube-abc', 'vimeo-42')
    upload = make_entry(vimeo_service, old, link='https://vimeo.com/42')
    like = make_entry(vimeo_service, old, link='https://vimeo.com/42', idata='liked')

    upgrades.apply(approve(upload, VIMEO, media_root))
    upgrades.apply(approve(like, VIMEO, media_root))

    rel = 'thumbs/%s/%s' % (NEW_THUMB[13], NEW_THUMB[13:])
    assert list(Media.objects.filter(entry=upload).values_list('file', flat=True)) == [
        rel
    ]
    assert not Media.objects.filter(entry=like).exists()


# -------------------------------------------------------------------- revert


def test_revert_puts_back_the_entry_and_queues_it_again(vimeo_service, media_root):
    old = YT_LEGACY[0].replace('youtube-abc', 'vimeo-42')
    entry = make_entry(vimeo_service, old, link='https://vimeo.com/42')
    kept = Media.objects.create(entry=entry, file='thumbs/a/%s' % OLD_THUMB[13:])
    upgrade = upgrades.apply(approve(entry, VIMEO, media_root))
    assert Media.objects.filter(entry=entry).count() == 2

    upgrades.revert(upgrade.pk)

    entry.refresh_from_db()
    assert (entry.content, entry.link, entry.mblob) == (
        old,
        'https://vimeo.com/42',
        None,
    )
    assert list(Media.objects.filter(entry=entry)) == [kept]
    upgrade.refresh_from_db()
    assert upgrade.status == EntryUpgrade.STATUS_REVERTED
    assert upgrade.reverted_at is not None
    assert [e.pk for e in upgrades.pending(VIMEO)] == [entry.pk]

    with pytest.raises(upgrades.UpgradeConflict):
        upgrades.revert(upgrade.pk)


def test_a_video_moved_to_youtube_leaves_the_vimeo_queue_until_reverted(
    vimeo_service, media_root
):
    old = YT_LEGACY[0].replace('youtube-abc', 'vimeo-42')
    entry = make_entry(vimeo_service, old, link='https://vimeo.com/42')
    token = approve(
        entry, VIMEO, media_root, values={'video': 'https://youtu.be/copy1'}
    )

    upgrade = upgrades.apply(token)

    entry.refresh_from_db()
    assert entry.content == yt_current('copy1')
    assert entry.link == 'https://www.youtube.com/watch?v=copy1'
    assert upgrades.pending(VIMEO) == []
    assert upgrades.pending(YT) == []

    upgrades.revert(upgrade.pk)

    entry.refresh_from_db()
    assert (entry.content, entry.link) == (old, 'https://vimeo.com/42')
    assert [e.pk for e in upgrades.pending(VIMEO)] == [entry.pk]


def test_revert_refuses_to_lose_a_later_edit(yt_service, media_root):
    entry = make_entry(yt_service, YT_LEGACY[0])
    upgrade = upgrades.apply(approve(entry, YT, media_root))
    Entry.objects.filter(pk=entry.pk).update(content='edited by hand')

    with pytest.raises(upgrades.UpgradeConflict, match='changed after'):
        upgrades.revert(upgrade.pk)

    entry.refresh_from_db()
    assert entry.content == 'edited by hand'
    upgrade.refresh_from_db()
    assert upgrade.status == EntryUpgrade.STATUS_APPLIED


def test_apply_and_revert_leave_the_dates_alone(yt_service, media_root):
    """An upgrade changes how an entry looks, never when it was published."""
    entry = make_entry(yt_service, YT_LEGACY[0])
    Entry.objects.filter(pk=entry.pk).update(
        date_published='2007-01-26T20:07:09Z',
        date_updated='2008-02-03T04:05:06Z',
        date_inserted='2009-07-18T05:16:54Z',
    )
    dates = ('date_published', 'date_updated', 'date_inserted')
    before = Entry.objects.filter(pk=entry.pk).values(*dates).get()

    upgrade = upgrades.apply(approve(Entry.objects.get(pk=entry.pk), YT, media_root))
    assert Entry.objects.filter(pk=entry.pk).values(*dates).get() == before

    upgrades.revert(upgrade.pk)
    assert Entry.objects.filter(pk=entry.pk).values(*dates).get() == before


# --------------------------------------------------------------- markup only


@pytest.fixture
def no_downloads():
    with (
        patch('glifestream.apis.youtube.media.save_image', side_effect=AssertionError),
        patch('glifestream.apis.vimeo.media.save_image', side_effect=AssertionError),
        patch(
            'glifestream.upgrades.videos.oembed.discover', side_effect=AssertionError
        ),
    ):
        yield


def test_markup_only_lists_entries_that_keep_their_thumbnail(
    yt_service, media_root, no_downloads
):
    put_thumb(media_root, NEW_THUMB)
    new_id = make_entry(yt_service, YT_LEGACY[-1])
    old_link = make_entry(
        yt_service, yt_current(), link='http://www.youtube.com/watch?v=abc'
    )
    make_entry(yt_service, YT_LEGACY[0])  # needs a new thumbnail
    make_entry(yt_service, yt_current())  # up to date

    found = upgrades.markup_only(YT)

    assert [e.pk for e, _p in found] == [new_id.pk, old_link.pk]
    assert all(p.content == yt_current() for _e, p in found)
    assert upgrades.counts(YT)['markup_only'] == 2


def test_apply_markup_only_applies_the_approved_entries_as_one_batch(
    yt_service, media_root, no_downloads
):
    put_thumb(media_root, NEW_THUMB)
    first = make_entry(yt_service, YT_LEGACY[-1], mblob=FLASH_MBLOB)
    second = make_entry(yt_service, YT_LEGACY[-1].replace('youtube-abc', 'youtube-def'))
    Entry.objects.filter(pk=first.pk).update(date_published='2014-05-06T07:08:09Z')
    first.refresh_from_db()
    published = first.date_published
    token = upgrades.make_batch_token(YT, [first, second])

    result = upgrades.apply_markup_only(token)

    assert (result.applied, result.refused) == (2, 0)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.content == yt_current()
    assert first.mblob is None
    assert first.date_published == published
    assert 'data-id="youtube-def"' in second.content
    assert set(EntryUpgrade.objects.values_list('batch', flat=True)) == {result.batch}
    assert upgrades.markup_only(YT) == []


def test_apply_markup_only_leaves_an_entry_changed_since_the_list(
    yt_service, media_root, no_downloads
):
    put_thumb(media_root, NEW_THUMB)
    kept = make_entry(yt_service, YT_LEGACY[-1])
    edited = make_entry(yt_service, YT_LEGACY[-1].replace('youtube-abc', 'youtube-def'))
    token = upgrades.make_batch_token(YT, [kept, edited])
    Entry.objects.filter(pk=edited.pk).update(content=edited.content + ' ')

    result = upgrades.apply_markup_only(token)

    assert (result.applied, result.refused) == (1, 1)
    edited.refresh_from_db()
    assert edited.content.endswith('</div> ')
    assert not EntryUpgrade.objects.filter(entry=edited).exists()


def test_apply_markup_only_refuses_a_forged_list(yt_service, media_root):
    put_thumb(media_root, NEW_THUMB)
    entry = make_entry(yt_service, YT_LEGACY[-1])
    token = upgrades.make_batch_token(YT, [entry])

    with pytest.raises(upgrades.UpgradeConflict):
        upgrades.apply_markup_only(token[:-2] + 'xx')
    # A single-entry approval does not pass for a batch, nor the other way.
    with pytest.raises(upgrades.UpgradeConflict):
        upgrades.apply(token)

    assert not EntryUpgrade.objects.exists()


def test_revert_batch_reverts_all_but_an_edited_entry(
    yt_service, media_root, no_downloads
):
    put_thumb(media_root, NEW_THUMB)
    first = make_entry(yt_service, YT_LEGACY[-1])
    second = make_entry(yt_service, YT_LEGACY[-1].replace('youtube-abc', 'youtube-def'))
    result = upgrades.apply_markup_only(upgrades.make_batch_token(YT, [first, second]))
    Entry.objects.filter(pk=second.pk).update(content='edited by hand')

    assert upgrades.revert_batch(result.batch) == (1, 1)

    first.refresh_from_db()
    assert first.content == YT_LEGACY[-1]
    second.refresh_from_db()
    assert second.content == 'edited by hand'
    assert upgrades.revert_batch('') == (0, 0)
