"""Upgrading old posts about a track to the music card."""

from __future__ import annotations

import datetime
import itertools
from unittest.mock import patch

import pytest
from PIL import Image

from glifestream import upgrades
from glifestream.filters import music
from glifestream.stream.models import Entry, EntryUpgrade, Media, Service

MUSIC = upgrades.UPGRADERS['music']

COVER = '[GLS-THUMBS]/1938a2f61cbe0bcdd49bdf6f7517accf9287a234.jpg'
YT_THUMB = '[GLS-THUMBS]/ad97b17ffccd1af56d7f1596ff2b47f4e6a487bf.webp'
SPOTIFY_COVER = 'https://image-cdn.spotifycdn.com/image/ab67616d00001e02'

# Posts as the owner's database stores them.
T61 = (
    '<p><span id="thesixtyone-thelace-rNLRv7Lq5If" class="play-audio">'
    '<a href="http://www.thesixtyone.com/thelace/song/BraveMen/rNLRv7Lq5If/" rel="nofollow">'
    'Brave Men</a></span> by The Impossible Shoelace</p>\n'
    '<p class="thumbnails">\n'
    '  <a href="http://www.thesixtyone.com/thelace/song/BraveMen/rNLRv7Lq5If/" rel="nofollow">'
    '<img src="%s" alt="thumbnail" /></a>\n</p>' % COVER
)
T61_PROSE = (
    "<p>One more Heavy Jack :) This time the nice Dire Straits' "
    '<span id="thesixtyone-heavyjack-ZlNw0yqolkJ" class="play-audio">'
    '<a href="http://www.thesixtyone.com/heavyjack/song/Six+Blade+Knife+/ZlNw0yqolkJ/" rel="nofollow">'
    'Six Blade Knife</a></span> cover.</p>\n'
    '<p class="thumbnails">\n'
    '  <a href="http://www.thesixtyone.com/heavyjack/song/Six+Blade+Knife+/ZlNw0yqolkJ/" rel="nofollow">'
    '<img src="%s" alt="thumbnail" /></a>\n</p>' % COVER
)
T61_NO_SPACES = (
    '<p><span id="thesixtyone-WWPJ-zlaKV8hcKw6" class="play-audio">'
    '<a href="http://www.thesixtyone.com/WWPJ/song/QuietLittleVoices/zlaKV8hcKw6/" rel="nofollow">'
    'QuietLittleVoices</a></span> by We Were Promised Jetpacks</p>'
)
SPOTIFY = (
    '<p><a href="https://open.spotify.com/track/1iRtIn5QGZ0mLoCoTm5lxo?si=Cv" rel="nofollow">'
    'Mattresses Underwater</a> by Colour Revolt</p>\n\n'
    '<iframe src="https://open.spotify.com/embed/track/1iRtIn5QGZ0mLoCoTm5lxo" '
    'width="300" height="80" frameborder="0" allowtransparency="true" '
    'allow="encrypted-media"></iframe>\n'
)
OWN_AUDIO = (
    '<p><span id="audio-a1174416" class="play-audio">'
    '<a href="https://example.org/music/Smells-Like-Me.ogg" rel="nofollow">'
    'Smells Like Me</a></span></p>\n<p>P.S. All the guitars are mine.</p>'
)

PUBLISHED = datetime.datetime(2009, 10, 16, 18, 35, 34, tzinfo=datetime.timezone.utc)
_guids = itertools.count(1)


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.APP_THUMBNAIL_FORMAT = 'WEBP'
    settings.BASE_URL = 'https://stream.example'
    return tmp_path


def put_image(media_root, internal: str, size=(160, 160)) -> None:
    name = internal.split('/', 1)[1]
    path = media_root / 'thumbs' / name[0] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', size).save(path, format='PNG')


@pytest.fixture
def selfposts(db):
    return Service.objects.create(name='Music', api='selfposts', cls='music')


def make_entry(service, content, **fields) -> Entry:
    values = {
        'title': 'Brave Men by The Impossible Shoelace',
        'link': 'http://www.thesixtyone.com/thelace/song/BraveMen/rNLRv7Lq5If/',
        'date_published': PUBLISHED,
        'date_updated': PUBLISHED,
    }
    values.update(fields)
    return Entry.objects.create(
        service=service, guid='guid-%d' % next(_guids), content=content, **values
    )


@pytest.fixture
def no_downloads():
    with patch(
        'glifestream.filters.music.media.save_image', side_effect=AssertionError
    ):
        yield


def card(artist, title, cover=None, vid=None) -> str:
    return music.card_html(music.Track(artist, title, cover, vid))


@pytest.mark.parametrize('content', [T61, T61_PROSE, T61_NO_SPACES, SPOTIFY, OWN_AUDIO])
def test_old_players_are_legacy(selfposts, content):
    assert MUSIC.is_legacy(make_entry(selfposts, content))


@pytest.mark.parametrize(
    'content',
    [
        '<p>Just words about <a href="https://open.spotify.com/track/x">a song</a>.</p>',
        '<p><span data-id="audio-1" class="play-audio"><a href="a.ogg">A</a></span></p>',
        card('Artist', 'Title'),
        '<p>Text</p>\n' + card('Artist', 'Title', None, 'abc'),
    ],
)
def test_current_posts_are_not_legacy(selfposts, content):
    assert not MUSIC.is_legacy(make_entry(selfposts, content))


def test_a_card_of_an_older_renderer_waits_again(selfposts, monkeypatch):
    entry = make_entry(selfposts, card('Artist', 'Title'))
    monkeypatch.setattr(
        music, 'LISTEN_ON', music.LISTEN_ON + (('Qobuz', 'https://q.example/%s', True),)
    )

    assert MUSIC.is_legacy(entry)
    proposal = MUSIC.propose_offline(entry)
    assert proposal is not None
    assert 'Qobuz' in proposal.content
    assert proposal.link == entry.link


def test_guess_reads_the_post(selfposts, media_root, no_downloads):
    put_image(media_root, COVER)

    assert MUSIC.guess(make_entry(selfposts, T61)) == {
        'artist': 'The Impossible Shoelace',
        'title': 'Brave Men',
        'youtube': '',
        'cover': COVER,
    }


def test_guess_prefers_the_spaced_title_and_skips_a_missing_cover(selfposts):
    entry = make_entry(selfposts, T61_NO_SPACES, title='Quiet Little Voices')
    prose = make_entry(selfposts, T61_PROSE, title='One more Heavy Jack :)')

    assert MUSIC.guess(entry)['title'] == 'Quiet Little Voices'
    assert MUSIC.guess(entry)['artist'] == 'We Were Promised Jetpacks'
    assert MUSIC.guess(prose)['artist'] == ''
    assert MUSIC.guess(prose)['cover'] == ''


def test_guess_takes_the_spotify_cover(selfposts):
    entry = make_entry(selfposts, SPOTIFY, title='Mattresses Underwater')
    with patch(
        'glifestream.upgrades.music.oembed.discover',
        return_value={'thumbnail_url': SPOTIFY_COVER},
    ) as discover:
        guess = MUSIC.guess(entry)

    discover.assert_called_once_with(
        'https://open.spotify.com/track/1iRtIn5QGZ0mLoCoTm5lxo', 'spotify'
    )
    assert guess['cover'] == SPOTIFY_COVER
    assert guess['artist'] == 'Colour Revolt'


def test_propose_replaces_the_player_with_a_card(selfposts, media_root):
    put_image(media_root, COVER)
    entry = make_entry(selfposts, T61)

    proposal = MUSIC.propose(
        entry,
        {
            'artist': 'The Impossible Shoelace',
            'title': 'Brave Men',
            'youtube': 'https://www.youtube.com/watch?v=xyz',
            'cover': COVER,
        },
    )

    assert proposal.content == card(
        'The Impossible Shoelace', 'Brave Men', music.Cover(COVER, 160, 160), 'xyz'
    )
    assert proposal.link == 'https://stream.example/'
    assert proposal.mblob is None


def test_propose_keeps_a_sentence_that_says_more(selfposts, media_root):
    put_image(media_root, COVER)
    entry = make_entry(selfposts, T61_PROSE)

    proposal = MUSIC.propose(
        entry, {'artist': 'Heavy Jack', 'title': 'Six Blade Knife', 'cover': COVER}
    )

    assert proposal.content == (
        "<p>One more Heavy Jack :) This time the nice Dire Straits' "
        'Six Blade Knife cover.</p>\n'
        + card('Heavy Jack', 'Six Blade Knife', music.Cover(COVER, 160, 160))
    )


def test_propose_of_a_sentence_without_a_thumbnail_adds_the_card_after_it(
    selfposts,
):
    content = T61_PROSE.split('\n<p class="thumbnails">')[0]
    entry = make_entry(selfposts, content + '\n<p>More.</p>')

    proposal = MUSIC.propose(
        entry, {'artist': 'Heavy Jack', 'title': 'Six Blade Knife'}
    )

    assert proposal.content == (
        "<p>One more Heavy Jack :) This time the nice Dire Straits' "
        'Six Blade Knife cover.</p>\n'
        + card('Heavy Jack', 'Six Blade Knife')
        + '\n<p>More.</p>'
    )


def test_propose_drops_the_spotify_player(selfposts, media_root):
    entry = make_entry(selfposts, SPOTIFY)

    proposal = MUSIC.propose(
        entry, {'artist': 'Colour Revolt', 'title': 'Mattresses Underwater'}
    )

    assert proposal.content == card('Colour Revolt', 'Mattresses Underwater')
    assert 'iframe' not in proposal.content


def test_propose_without_the_artist_is_unavailable(selfposts):
    entry = make_entry(selfposts, T61_PROSE, title='One more Heavy Jack :)')

    with pytest.raises(upgrades.Unavailable, match='artist and the title'):
        MUSIC.propose(entry)


def test_a_bad_youtube_address_is_unavailable(selfposts):
    entry = make_entry(selfposts, T61)

    with pytest.raises(upgrades.Unavailable, match='YouTube'):
        MUSIC.propose(entry, {'artist': 'A', 'title': 'T', 'youtube': 'nope'})


def test_own_audio_only_changes_its_id(selfposts):
    entry = make_entry(selfposts, OWN_AUDIO, link='https://example.org/stream/')

    proposal = MUSIC.propose_offline(entry)

    assert proposal is not None
    assert proposal.content == OWN_AUDIO.replace('id="audio-', 'data-id="audio-')
    assert proposal.link == entry.link
    assert MUSIC.propose(entry) == proposal


def test_only_own_audio_is_markup_only(selfposts):
    make_entry(selfposts, T61)
    own = make_entry(selfposts, OWN_AUDIO)

    assert [e.pk for e, _p in upgrades.markup_only(MUSIC)] == [own.pk]


def test_the_scan_looks_at_posts_only(selfposts, db):
    other = Service.objects.create(name='Blog', api='webfeed')
    make_entry(other, T61)
    post = make_entry(selfposts, T61)

    assert [e.pk for e in upgrades.pending(MUSIC)] == [post.pk]


def test_apply_and_revert_keep_the_dates(selfposts, media_root):
    put_image(media_root, COVER)
    entry = make_entry(selfposts, T61)
    Media.objects.create(entry=entry, file='thumbs/1/' + COVER.split('/')[1])
    values = {'artist': 'The Impossible Shoelace', 'title': 'Brave Men', 'cover': COVER}
    proposal = MUSIC.propose(entry, values)

    upgrade = upgrades.apply(upgrades.make_token(entry, MUSIC, proposal))

    entry.refresh_from_db()
    assert entry.content == proposal.content
    assert entry.link == 'https://stream.example/'
    assert (entry.date_published, entry.date_updated) == (PUBLISHED, PUBLISHED)
    assert not upgrades.pending(MUSIC)
    assert Media.objects.filter(entry=entry).count() == 1

    upgrades.revert(upgrade.pk)

    entry.refresh_from_db()
    assert entry.content == T61
    assert entry.link.startswith('http://www.thesixtyone.com/')
    assert entry.date_published == PUBLISHED
    assert EntryUpgrade.objects.get().status == EntryUpgrade.STATUS_REVERTED
