"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.

The music card in the browser: posting one from the composer, and turning
an old post about a track into one on the Upgrades page.

The live server runs in this process, so the video thumbnail is stubbed
where the card would download it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings
from PIL import Image
from playwright.sync_api import Page, expect

from glifestream.filters import music
from glifestream.stream.models import Entry, Service

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

OLD_COVER = 'c0e2e00000000000000000000000000000cover0.jpg'
VIDEO_THUMB = 'd0e2e00000000000000000000000000000thumb0.webp'
OLD_POST = (
    '<p><span id="thesixtyone-band-e2eSong01" class="play-audio">'
    '<a href="http://www.thesixtyone.com/band/song/E2eSong/e2eSong01/" rel="nofollow">'
    'E2e Song</a></span> by The E2e Band</p>\n'
    '<p class="thumbnails">\n'
    '  <a href="http://www.thesixtyone.com/band/song/E2eSong/e2eSong01/" rel="nofollow">'
    '<img src="[GLS-THUMBS]/%s" alt="thumbnail" /></a>\n</p>' % OLD_COVER
)
EMBED = 'https://www.youtube.com/embed/e2eTrack01?autoplay=1&rel=0'


def _image(name: str, size: tuple[int, int]) -> None:
    path = Path(settings.MEDIA_ROOT) / 'thumbs' / name[0] / name
    Image.new('RGB', size, (160, 60, 40)).save(path)


@pytest.fixture
def video_thumbnail(monkeypatch) -> None:
    _image(VIDEO_THUMB, (320, 180))
    monkeypatch.setattr(
        'glifestream.filters.music.media.save_image',
        lambda url, **kwargs: '[GLS-THUMBS]/%s' % VIDEO_THUMB,
    )


@pytest.fixture
def old_music_post() -> Entry:
    _image(OLD_COVER, (160, 160))
    service = Service.objects.create(name='Music', api='selfposts', cls='music')
    return Entry.objects.create(
        service=service,
        guid='tag:e2e,2009:stream/entry/music',
        title='E2e Song by The E2e Band',
        link='http://www.thesixtyone.com/band/song/E2eSong/e2eSong01/',
        content=OLD_POST,
    )


def test_post_a_music_track_from_the_composer(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    stub_external_requests,
    notes_service: Service,
    video_thumbnail,
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    page.locator('#ashare').click()
    page.locator('#expand-sharing').click()
    fields = page.locator('#music-track')
    # Folded until the owner asks for it.
    expect(fields.get_by_label('Artist')).to_be_hidden()
    fields.get_by_text('Music track').click()

    fields.get_by_label('Artist').fill('The E2e Band')
    fields.get_by_label('Title').fill('E2e Song')
    fields.get_by_label('YouTube video').fill('https://youtu.be/e2eTrack01')
    # A track is a post of its own, with nothing typed in the editor.
    page.locator('#post').click()

    card = page.locator('#stream article.hentry').first.locator('.music-card')
    expect(card.locator('.music-title')).to_have_text('E2e Song')
    expect(card.locator('.music-artist')).to_have_text('The E2e Band')
    expect(card.locator('.music-links a')).to_have_count(6)
    expect(fields.get_by_label('Artist')).to_have_value('')
    expect(fields).not_to_have_attribute('open', '')

    card.locator('.play-video').click()
    expect(card.locator('div.player.video.youtube iframe')).to_have_attribute(
        'src', EMBED
    )

    entry = Entry.objects.get(content__contains='music-card')
    assert entry.title == 'E2e Song – The E2e Band'
    assert entry.service == notes_service


def test_upgrade_an_old_music_post(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    stub_external_requests,
    old_music_post: Entry,
    video_thumbnail,
):
    entry = old_music_post
    published = entry.date_published
    ensure_admin_session()

    page.goto(f'{app_base_url}/settings/upgrades')
    row = page.locator('tr[data-upgrader="music"]')
    expect(row.locator('.pending')).to_have_text('1')
    row.get_by_role('link', name='Review').click()

    form = page.locator('form.upgrade-fields')
    expect(form.get_by_label('Artist')).to_have_value('The E2e Band')
    expect(form.get_by_label('Title')).to_have_value('E2e Song')
    expect(form.get_by_label('Cover image')).to_have_value(f'[GLS-THUMBS]/{OLD_COVER}')
    expect(form.get_by_role('link', name='Search')).to_have_attribute(
        'href', 'https://www.youtube.com/results?search_query=The+E2e+Band+E2e+Song'
    )

    form.get_by_label('YouTube video').fill(
        'https://www.youtube.com/watch?v=e2eTrack01'
    )
    form.get_by_role('button', name='Preview B').click()

    after = page.locator('#stream.upgrade-compare > article').last
    card = after.locator('.music-card')
    expect(card.locator('img')).to_have_attribute('src', f'/media/thumbs/c/{OLD_COVER}')
    card.locator('.play-video').click()
    expect(card.locator('div.player.video.youtube iframe')).to_have_attribute(
        'src', EMBED
    )

    page.get_by_role('button', name='Apply B').click()
    expect(page.locator('.upgrade-messages .done')).to_contain_text(
        f'Applied to entry #{entry.pk}.'
    )
    expect(page.get_by_text('All Music entries are up to date.')).to_be_visible()

    entry.refresh_from_db()
    assert 'thesixtyone' not in entry.content
    assert 'data-id="youtube-e2eTrack01"' in entry.content
    assert entry.date_published == published


def test_edit_a_music_post_with_its_fields_and_class(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    stub_external_requests,
    notes_service: Service,
    make_entry,
):
    _image(OLD_COVER, (160, 160))
    Service.objects.filter(pk=notes_service.pk).update(public=True)
    music_service = Service.objects.create(
        name='Music', api='selfposts', cls='music', public=True
    )
    track = music.Track(
        'The E2e Band', 'E2e Song', music.Cover('[GLS-THUMBS]/%s' % OLD_COVER, 160, 160)
    )
    entry = make_entry('E2e Song – The E2e Band', music.card_html(track))
    Entry.objects.filter(pk=entry.pk).update(service=music_service)
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = page.locator(f'#entry-{entry.pk}')

    article.locator('.entry-controls-switch').click()
    article.locator('.entry-controls .edit-control').click()

    # The editor shows the card, its fields edit it, and the post is in its class.
    card = page.locator('#status-editor .editor-music-card')
    expect(card.locator('.music-title')).to_have_text('E2e Song')
    expect(card.locator('img')).to_have_attribute('src', f'/media/thumbs/c/{OLD_COVER}')
    fields = page.locator('#music-track')
    expect(fields).to_have_attribute('open', '')
    expect(fields.get_by_label('Artist')).to_have_value('The E2e Band')
    expect(fields.get_by_label('Cover image')).to_have_value(
        f'/media/thumbs/c/{OLD_COVER}'
    )
    expect(page.locator('#status-class option:checked')).to_have_text('music')

    preview = page.locator('#stream > article.entry-preview')
    expect(preview).to_have_class(re.compile(r'\be-music\b'))
    page.locator('#status-class').select_option(label=notes_service.cls)
    fields.get_by_label('Title').fill('E2e Song (live)')
    expect(card.locator('.music-title')).to_have_text('E2e Song (live)')
    expect(preview).to_have_class(re.compile(rf'\be-{notes_service.cls}\b'))
    expect(preview.locator('.music-title')).to_have_text('E2e Song (live)')

    page.locator('#update').click()

    saved = page.locator(f'#entry-{entry.pk}')
    expect(saved).to_have_class(re.compile(rf'\be-{notes_service.cls}\b'))
    expect(saved.locator('.music-title')).to_have_text('E2e Song (live)')
    entry.refresh_from_db()
    assert entry.service == notes_service
    assert entry.content.startswith('<div class="music-card">')
    assert '[GLS-THUMBS]/%s' % OLD_COVER in entry.content

    # Taking the card out of the editor empties its fields.
    card.click()
    page.keyboard.press('Delete')
    expect(fields.get_by_label('Artist')).to_have_value('')
