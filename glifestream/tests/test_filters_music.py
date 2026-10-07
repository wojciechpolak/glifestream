"""The music card: its markup, reading it back, and its cover."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import Image

from glifestream.filters import music
from glifestream.utils import httpclient

COVER = '[GLS-THUMBS]/1938a2f61cbe0bcdd49bdf6f7517accf9287a234.jpg'
YT_THUMB = '[GLS-THUMBS]/ad97b17ffccd1af56d7f1596ff2b47f4e6a487bf.webp'


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.APP_THUMBNAIL_FORMAT = 'WEBP'
    return tmp_path


def put_image(media_root, internal: str, size=(160, 160)) -> None:
    """Write a picture of `size` behind a [GLS-THUMBS] reference."""
    name = internal.split('/', 1)[1]
    path = media_root / 'thumbs' / name[0] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', size).save(path, format='PNG')


TRACK = music.Track(
    artist='Angus & Julia Stone',
    title='Big Jet Plane',
    cover=music.Cover(COVER, 160, 160),
    youtube_id='abc-123',
)


def test_card_plays_the_video_from_its_cover():
    html = music.card_html(TRACK)

    assert html.startswith('<div class="music-card"><div data-id="youtube-abc-123"')
    assert ' id="' not in html
    assert '<a href="https://www.youtube.com/watch?v=abc-123" rel="nofollow">' in html
    assert (
        '<img src="%s" width="160" height="160" '
        'alt="Big Jet Plane – Angus &amp; Julia Stone" />' % COVER
    ) in html
    assert '<div class="playbutton"></div>' in html
    assert '<span class="music-title">Big Jet Plane</span>' in html
    assert '<span class="music-artist">Angus &amp; Julia Stone</span>' in html


def test_card_links_a_search_on_each_service():
    html = music.card_html(TRACK)

    for name, _url, _in_path in music.LISTEN_ON:
        assert '>%s</a>' % name in html
    assert (
        'https://open.spotify.com/search/Angus%20%26%20Julia%20Stone%20Big%20Jet%20Plane'
        in html
    )
    assert (
        'https://music.apple.com/search?term=Angus+%26+Julia+Stone+Big+Jet+Plane'
        in html
    )
    assert (
        'https://bandcamp.com/search?q=Angus+%26+Julia+Stone+Big+Jet+Plane&amp;item_type=t'
        in html
    )


def test_card_without_a_video_or_a_cover():
    no_video = music.card_html(
        music.Track('Artist', 'Title', music.Cover(COVER, 160, 160))
    )
    text_only = music.card_html(music.Track('Artist', 'Title'))

    assert 'play-video' not in no_video
    assert '<span class="music-cover"><img src="%s"' % COVER in no_video
    assert '<img' not in text_only and 'play-video' not in text_only
    assert '<span class="music-title">Title</span>' in text_only


def test_card_escapes_what_the_owner_typed():
    html = music.card_html(music.Track('<b>A</b>', 'T "q"'))

    assert '<b>' not in html
    assert '&lt;b&gt;A&lt;/b&gt;' in html
    assert 'T &quot;q&quot;' in html


@pytest.mark.parametrize(
    'track',
    [
        TRACK,
        music.Track("I've Got Friends", 'Manchester Orchestra'),
        music.Track('A', 'B', music.Cover(COVER, 175, 175)),
        music.Track('A', 'B', None, 'xyz'),
    ],
)
def test_a_card_reads_back_as_its_track(track):
    assert music.parse_card(music.card_html(track)) == track


def test_find_card_spans_the_whole_card():
    card = music.card_html(TRACK)
    content = '<p>Before</p>\n%s\n<div>after</div>' % card

    found = music.find_card(content)

    assert found is not None
    assert content[found[0] : found[1]] == card
    assert music.find_card(content, found[1]) is None


@pytest.mark.parametrize(
    'url, vid',
    [
        ('https://www.youtube.com/watch?v=abc', 'abc'),
        (' https://youtu.be/abc ', 'abc'),
        ('https://music.youtube.com/watch?v=abc&list=x', 'abc'),
        ('https://vimeo.com/123', None),
        ('nonsense', None),
    ],
)
def test_youtube_id(url, vid):
    assert music.youtube_id(url) == vid


def test_a_local_cover_keeps_its_file_and_size(media_root):
    put_image(media_root, COVER, size=(175, 175))

    assert music.localize_cover(COVER) == music.Cover(COVER, 175, 175)


def test_a_missing_local_cover_is_an_error():
    with pytest.raises(music.MusicError):
        music.localize_cover(COVER)


def test_a_local_cover_that_is_no_picture_is_an_error(media_root):
    name = COVER.split('/', 1)[1]
    path = media_root / 'thumbs' / name[0] / name
    path.parent.mkdir(parents=True)
    path.write_bytes(b'not a picture')

    with pytest.raises(music.MusicError, match='not a picture'):
        music.localize_cover(COVER)


def test_a_remote_cover_is_saved_scaled_down(media_root):
    put_image(media_root, YT_THUMB, size=(160, 120))
    with patch(
        'glifestream.filters.music.media.save_image', return_value=YT_THUMB
    ) as save:
        cover = music.localize_cover('https://img.example/c.jpg')

    save.assert_called_once_with(
        'https://img.example/c.jpg', downscale=True, size=music.COVER_SIZE, strict=True
    )
    assert cover == music.Cover(YT_THUMB, 160, 120)


def _not_found(url):
    return httpclient.build_fetch_error(
        category='not_found',
        detail='HTTP 404',
        retryable=False,
        status_code=404,
        url=url,
    )


def test_a_cover_that_is_not_there_is_an_error():
    url = 'https://img.example/gone.jpg'
    with patch(
        'glifestream.filters.music.media.save_image', side_effect=_not_found(url)
    ):
        with pytest.raises(music.MusicError, match='no image') as raised:
            music.localize_cover(url)
    assert raised.value.gone
    with pytest.raises(music.MusicError):
        music.localize_cover('file:///etc/passwd')


def test_a_cover_that_cannot_be_saved_says_why():
    denied = PermissionError(13, 'Permission denied', '/media/thumbs/a/x.webp')
    with patch('glifestream.filters.music.media.save_image', side_effect=denied):
        with pytest.raises(music.MusicError, match='Permission denied') as raised:
            music.localize_cover('https://img.example/c.jpg')
    assert not raised.value.gone


def test_build_track_tells_a_missing_video_thumbnail_from_a_failure():
    vid_thumb = music.YOUTUBE_THUMBNAIL_URL % 'abc'
    with patch(
        'glifestream.filters.music.media.save_image', side_effect=_not_found(vid_thumb)
    ):
        with pytest.raises(music.MusicError, match='Enter a cover'):
            music.build_track('A', 'T', 'https://youtu.be/abc')
    with patch(
        'glifestream.filters.music.media.save_image',
        side_effect=PermissionError(13, 'Permission denied'),
    ):
        with pytest.raises(music.MusicError, match='Permission denied'):
            music.build_track('A', 'T', 'https://youtu.be/abc')


def test_build_track_falls_back_to_the_video_thumbnail(media_root):
    put_image(media_root, YT_THUMB, size=(320, 180))
    with patch(
        'glifestream.filters.music.media.save_image', return_value=YT_THUMB
    ) as save:
        track = music.build_track(' Artist ', 'Title\n', 'https://youtu.be/abc')

    assert save.call_args.args[0] == 'https://i.ytimg.com/vi/abc/mqdefault.jpg'
    assert track == music.Track(
        'Artist', 'Title', music.Cover(YT_THUMB, 320, 180), 'abc'
    )


def test_build_track_needs_the_artist_and_the_title():
    with pytest.raises(music.MusicError, match='artist and the title'):
        music.build_track('', 'Title')


def test_build_track_strict_or_lenient_about_a_bad_address(caplog):
    with pytest.raises(music.MusicError, match='YouTube'):
        music.build_track('A', 'T', 'https://vimeo.com/1')
    with pytest.raises(music.MusicError):
        music.build_track('A', 'T', cover_url=COVER)

    track = music.build_track('A', 'T', 'https://vimeo.com/1', COVER, strict=False)

    assert track == music.Track('A', 'T')
    assert 'without its player' in caplog.text
    assert 'without its cover' in caplog.text


def test_render_cards_makes_each_card_again_from_what_it_shows(media_root):
    put_image(media_root, COVER, size=(175, 175))
    edited = (
        '<div>Intro</div><div class="music-card"><span class="music-cover">'
        '<img src="%s" width="0" height="0" alt=""></span><p class="music-track">'
        '<span class="music-title">Big Jet Plane</span> <span class="music-artist">'
        'Angus &amp; Julia Stone</span></p><p class="music-links"></p></div>' % COVER
    )
    nameless = '<div class="music-card"><p class="music-track"></p></div>'

    out, title = music.render_cards(edited + nameless)

    track = music.Track(
        'Angus & Julia Stone', 'Big Jet Plane', music.Cover(COVER, 175, 175)
    )
    assert out == '<div>Intro</div>' + music.card_html(track)
    assert title == 'Big Jet Plane – Angus & Julia Stone'
    assert music.strip_cards(out) == '<div>Intro</div>'
    assert music.render_cards('<p>No card</p>') == ('<p>No card</p>', '')
