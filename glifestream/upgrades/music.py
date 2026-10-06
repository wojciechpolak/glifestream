"""
# gLifestream Copyright (C) 2026 Wojciech Polak
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# Posts about a track, turned into a music card.
#
# Old posts played a track on thesixtyone.com, which is gone, or in a
# Spotify player that loads with the page. Neither says which video plays
# the track, so the owner tells it on the review page; the upgrader only
# guesses the artist, the title and the cover from the post.

from __future__ import annotations

import html
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from django.conf import settings
from django.utils.html import escape, strip_tags
from django.utils.translation import gettext_noop

from glifestream.filters import music
from glifestream.stream import media
from glifestream.stream.models import Entry
from glifestream.upgrades.types import Field, Proposal, Unavailable
from glifestream.utils import oembed

# An old player of a track: a thesixtyone link, or a link to a Spotify track.
_SONG = re.compile(
    r'<span (?:data-)?id="thesixtyone-[^"]*" class="play-audio">'
    r'<a\b[^>]*>(?P<t61>.*?)</a></span>'
    r'|<a href="(?P<spotify>https://open\.spotify\.com/track/[^"]+)"[^>]*>'
    r'(?P<st>.*?)</a>',
    re.S,
)
# What only shows that player and goes with it.
_PLAYER_BLOCK = re.compile(
    r'<p class="thumbnails">\s*<a href="https?://www\.thesixtyone\.com/[^"]*"'
    r'[^>]*>.*?</a>\s*</p>'
    r'|<iframe\b[^>]*\bsrc="https://open\.spotify\.com/embed/[^"]*"[^>]*>\s*</iframe>',
    re.S,
)
_SPOTIFY_EMBED = 'open.spotify.com/embed/'
# An own audio file, from before data-id replaced the id.
_AUDIO_ID = re.compile(r'<span id="(audio-[^"]*)" class="play-audio">')
# Links of the post to a player that no longer plays.
_DEAD_LINK = re.compile(r'https?://(?:www\.)?(?:thesixtyone\.com|open\.spotify\.com)/')


@dataclass
class _Song:
    """The old player of a track in a post, and what goes with it."""

    start: int
    end: int
    text: str
    # The paragraph the player is in, if it says no more than the card.
    paragraph: tuple[int, int] | None
    # The artist the paragraph names: "<title> by <artist>".
    artist: str
    spotify: str
    blocks: list[tuple[int, int]] = field(default_factory=list)
    cover: str = ''


def _text(fragment: str) -> str:
    return music.clean(html.unescape(strip_tags(fragment)))


def _paragraph(content: str, start: int, end: int) -> tuple[int, int] | None:
    """Where the <p> around content[start:end] begins and ends, if any."""
    begin = max(content.rfind('<p>', 0, start), content.rfind('<p ', 0, start))
    if begin == -1 or content.find('</p>', begin, start) != -1:
        return None
    close = content.find('</p>', end)
    return (begin, close + len('</p>')) if close != -1 else None


def _find_song(content: str) -> _Song | None:
    m = _SONG.search(content)
    if m is None:
        return None
    spotify = m.group('spotify') or ''
    if spotify and _SPOTIFY_EMBED not in content:
        # A link to a track, not a player: the post is fine as it is.
        return None
    song = _Song(
        start=m.start(),
        end=m.end(),
        text=_text(m.group('t61') or m.group('st') or ''),
        paragraph=None,
        artist='',
        spotify=spotify,
    )
    para = _paragraph(content, m.start(), m.end())
    if para is not None:
        rest = _text(content[m.end() : para[1]])
        before = _text(content[para[0] : m.start()])
        by = re.fullmatch(r'by\s+(.+)', rest)
        if by:
            song.artist = by.group(1)
        if not before and (not rest or by):
            song.paragraph = para
    for block in _PLAYER_BLOCK.finditer(content):
        song.blocks.append((block.start(), block.end()))
        img = re.search(r'<img\b[^>]*\bsrc="(\[GLS-THUMBS\]/[^"]+)"', block.group(0))
        if img and not song.cover:
            song.cover = img.group(1)
    return song


def _same_words(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return re.sub(r'\W+', '', s).lower()

    return norm(a) == norm(b)


def _cover_on_disk(src: str) -> bool:
    return bool(src) and all(
        os.path.isfile(os.path.join(settings.MEDIA_ROOT, rel))
        for rel in media.thumb_rels(src)
    )


def _replace_song(content: str, song: _Song, card: str) -> str:
    """`content` with the old player of `song` replaced by `card`.

    The card takes the place of the first thing removed: the paragraph
    that only named the track, or the player's thumbnail or frame. A
    paragraph that says more keeps the track's name as text, and the card
    follows it when nothing else is removed.
    """
    edits = [(a, b, '') for a, b in song.blocks]
    if song.paragraph is not None:
        edits.append((song.paragraph[0], song.paragraph[1], ''))
    else:
        edits.append((song.start, song.end, escape(song.text)))
    edits.sort()
    removed = [i for i, edit in enumerate(edits) if edit[2] == '']
    if removed:
        a, b, _r = edits[removed[0]]
        edits[removed[0]] = (a, b, card)
    else:
        para = _paragraph(content, song.start, song.end)
        at = para[1] if para else song.end
        edits.append((at, at, card))
        edits.sort()

    out = ''
    last = 0
    for a, b, replacement in edits:
        chunk = content[last:a]
        if replacement == '' or replacement == card:
            # A block on its own line, without the blank lines around it.
            out = (out + chunk).rstrip()
            out += '\n' + replacement if replacement and out else replacement
        else:
            out += chunk + replacement
        last = b
        if replacement == '' or replacement == card:
            rest = content[last:]
            last += len(rest) - len(rest.lstrip())
    tail = content[last:]
    return (out + ('\n' + tail if tail and out else tail)).strip()


def _rerender_cards(content: str) -> str:
    """`content` with every card it shows made again by today's renderer.
    A card that cannot be read stays as it is."""
    out = []
    pos = 0
    while (found := music.find_card(content, pos)) is not None:
        begin, end = found
        track = music.parse_card(content[begin:end])
        out.append(content[pos:begin])
        out.append(music.card_html(track) if track else content[begin:end])
        pos = end
    out.append(content[pos:])
    return ''.join(out)


def _offline_content(content: str) -> str:
    content = _AUDIO_ID.sub(r'<span data-id="\1" class="play-audio">', content)
    return _rerender_cards(content)


class MusicUpgrader:
    key = 'music'
    api = 'selfposts'
    label = 'Music'
    markers: tuple[str, ...] = (
        'thesixtyone-',
        _SPOTIFY_EMBED,
        'class="music-card"',
        'id="audio-',
    )
    fields: tuple[Field, ...] = (
        Field('artist', gettext_noop('Artist')),
        Field('title', gettext_noop('Title')),
        Field('youtube', gettext_noop('YouTube video')),
        Field('cover', gettext_noop('Cover image')),
    )

    def is_legacy(self, entry: Entry) -> bool:
        if _find_song(entry.content) is not None:
            return True
        proposal = self.propose_offline(entry)
        return proposal is not None and not proposal.matches(entry)

    def guess(self, entry: Entry) -> dict[str, str]:
        song = _find_song(entry.content)
        if song is None:
            return {}
        title, artist = song.text, song.artist
        named = entry.title.split(' by ', 1)
        if _same_words(title, named[0]) or re.match(r'https?://', title):
            title = named[0]
        if not artist and len(named) == 2:
            artist = named[1]
        cover = song.cover if _cover_on_disk(song.cover) else ''
        if not cover and song.spotify:
            data = oembed.discover(song.spotify.split('?')[0], 'spotify')
            url = data.get('thumbnail_url') if isinstance(data, dict) else None
            cover = url or ''
        return {
            'artist': music.clean(artist),
            'title': music.clean(title),
            'youtube': '',
            'cover': cover,
        }

    def field_help(self, entry: Entry, name: str, values: Mapping[str, str]) -> str:
        if name != 'youtube':
            return ''
        q = music.clean('%s %s' % (values.get('artist', ''), values.get('title', '')))
        return 'https://www.youtube.com/results?search_query=%s' % quote_plus(q)

    def propose_offline(self, entry: Entry) -> Proposal | None:
        if _find_song(entry.content) is not None:
            # Only the owner knows which video plays the track.
            return None
        return Proposal(
            content=_offline_content(entry.content),
            link=entry.link,
            mblob=entry.mblob,
        )

    def propose(
        self, entry: Entry, values: Mapping[str, str] | None = None
    ) -> Proposal:
        song = _find_song(entry.content)
        if song is None:
            proposal = self.propose_offline(entry)
            assert proposal is not None
            return proposal
        if values is None:
            values = self.guess(entry)
        try:
            track = music.build_track(
                values.get('artist', ''),
                values.get('title', ''),
                values.get('youtube', ''),
                values.get('cover', ''),
            )
        except music.MusicError as exc:
            raise Unavailable(str(exc)) from exc
        content = _replace_song(entry.content, song, music.card_html(track))
        link = entry.link
        if _DEAD_LINK.match(link or ''):
            link = settings.BASE_URL + '/'
        return Proposal(content=_offline_content(content), link=link, mblob=entry.mblob)

    def registers_media(self, entry: Entry) -> bool:
        # As a post does: its pictures are its media.
        return True
