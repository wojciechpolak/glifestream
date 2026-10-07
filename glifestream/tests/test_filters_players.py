"""The players of videos in an entry's content: finding them and making
them again in today's markup."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from glifestream.filters import music, players

OLD_THUMB = '[GLS-THUMBS]/aa48110be7944fd483b96f1e7310372310cbf556.jpg'
NEW_THUMB = '[GLS-THUMBS]/ad97b17ffccd1af56d7f1596ff2b47f4e6a487bf.webp'
OLD_PLAYER = (
    '<table class="vc"><tr><td><div data-id="youtube-2yOVITOeY0g" class="play-video">'
    '<a href="https://www.youtube.com/watch?v=2yOVITOeY0g" rel="nofollow">'
    '<img src="%s" width="200" height="150" alt="YouTube Video" /></a>'
    '<div class="playbutton"></div></div></td></tr></table>' % OLD_THUMB
)
POST = '<p>Nirvana - Aneurysm (guitar cover)</p>\n' + OLD_PLAYER


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


def current(vid='2yOVITOeY0g', src=NEW_THUMB, provider='youtube') -> str:
    return players.player_html(provider, vid, src)


def test_find_blocks_takes_the_wrapping_table_and_paragraph():
    wrapped = '<p>Intro</p>\n<p>%s</p>\n<p>Outro</p>' % OLD_PLAYER

    [block] = players.find_blocks(wrapped)

    assert wrapped[block.start : block.end] == '<p>%s</p>' % OLD_PLAYER
    assert (block.provider, block.video_id) == ('youtube', '2yOVITOeY0g')
    assert (block.src, block.width, block.height) == (OLD_THUMB, '200', '150')


def test_find_blocks_reads_old_ids_and_vimeo_and_keeps_a_shared_paragraph():
    content = (
        '<p>Look: <div class="play-video" id="vimeo-42"><a href="http://vimeo.com/42">'
        '<img alt="x" src="https://i.vimeocdn.com/42.jpg" width="320" height="180"/>'
        '</a><div class="playbutton"></div></div></p>'
    )

    [block] = players.find_blocks(content)

    assert (block.provider, block.video_id, block.alt) == ('vimeo', '42', 'x')
    assert content[block.start : block.end].startswith('<div class="play-video"')
    assert content[block.end :] == '</p>'


def test_find_blocks_leaves_the_player_of_a_music_card():
    card = music.card_html(
        music.Track('A', 'T', music.Cover(OLD_THUMB, 160, 160), 'abc')
    )

    assert players.find_blocks(card + OLD_PLAYER)[0].video_id == '2yOVITOeY0g'
    assert players.find_blocks(card) == []


def test_canonical_keeps_a_current_thumbnail_and_unwraps_the_table(media_root):
    put_thumb(media_root, NEW_THUMB)
    stale = POST.replace(OLD_THUMB, NEW_THUMB).replace(
        'width="200" height="150"', 'width="320" height="180"'
    )

    assert players.canonical(stale, public=True) == (
        '<p>Nirvana - Aneurysm (guitar cover)</p>\n' + current()
    )
    # The old thumbnail needs a new one, which only `render` fetches.
    assert players.canonical(POST, public=True) is None


def test_render_fetches_a_new_thumbnail():
    with patch(
        'glifestream.filters.players.media.save_image', return_value=NEW_THUMB
    ) as save:
        out = players.render(POST, public=True)

    save.assert_called_once_with(
        'https://i.ytimg.com/vi/2yOVITOeY0g/mqdefault.jpg',
        downscale=True,
        size=(320, 180),
        strict=False,
    )
    assert out == '<p>Nirvana - Aneurysm (guitar cover)</p>\n' + current()


def test_render_plays_another_video_in_the_first_player():
    second = OLD_PLAYER.replace('2yOVITOeY0g', 'second01')
    with (
        patch(
            'glifestream.filters.players.oembed.discover',
            return_value={'thumbnail_url': 'https://i.vimeocdn.com/77.jpg'},
        ),
        patch('glifestream.filters.players.media.save_image', return_value=NEW_THUMB),
    ):
        out = players.render(OLD_PLAYER + second, public=True, replace=('vimeo', '77'))

    assert out == current('77', provider='vimeo') + current('second01')


def test_render_keeps_the_title_a_vimeo_player_named(media_root):
    put_thumb(media_root, NEW_THUMB)
    named = players.player_html('vimeo', '42', NEW_THUMB, 'Trip & back')

    assert 'alt="Trip &amp; back"' in named
    assert players.canonical(named, public=True) == named
    replaced = players.render(
        named, public=True, thumbnail=lambda p, v: NEW_THUMB, replace=('vimeo', '7')
    )
    assert 'alt="Vimeo Video"' in replaced


def test_render_with_its_own_thumbnails_and_a_private_service():
    seen = []

    def thumbnail(provider, vid):
        seen.append((provider, vid))
        return None

    # No thumbnail for the same video keeps the one shown.
    assert 'src="%s"' % OLD_THUMB in players.render(
        POST, public=True, thumbnail=thumbnail
    )
    # Nor for another one: a link to it stays instead.
    assert players.render(
        OLD_PLAYER, public=True, thumbnail=thumbnail, replace=('youtube', 'n1')
    ) == (
        '<a href="https://www.youtube.com/watch?v=n1" rel="nofollow">'
        'https://www.youtube.com/watch?v=n1</a>'
    )
    assert seen == [('youtube', '2yOVITOeY0g'), ('youtube', 'n1')]

    with patch('glifestream.filters.players.media.save_image') as save:
        out = players.render(OLD_PLAYER, public=False)
    save.assert_not_called()
    assert 'src="https://i.ytimg.com/vi/2yOVITOeY0g/mqdefault.jpg"' in out


@pytest.mark.parametrize(
    'url, video',
    [
        ('https://youtu.be/abc', ('youtube', 'abc')),
        ('https://vimeo.com/42', ('vimeo', '42')),
        ('https://example.com/42', None),
    ],
)
def test_video_of(url, video):
    assert players.video_of(url) == video
