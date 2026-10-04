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

Reviewing, applying and reverting an entry upgrade in the browser.

The live server runs in this process, so the new thumbnail is stubbed where
the provider would download it. Rows are created before the page loads and
checked only after the page shows the response.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from PIL import Image
from playwright.sync_api import Page, expect

from glifestream.stream.models import Entry, Service

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

OLD_THUMB = 'a0e2e0000000000000000000000000000000old0.jpg'
NEW_THUMB = 'b0e2e0000000000000000000000000000000new0.webp'
OLD_CONTENT = (
    '<table class="vc"><tr><td><div id="youtube-e2eVideo01" class="play-video">'
    '<a href="https://www.youtube.com/watch?v=e2eVideo01" rel="nofollow">'
    '<img src="[GLS-THUMBS]/%s" width="200" height="150" alt="YouTube Video" />'
    '</a><div class="playbutton"></div></div></td></tr></table>' % OLD_THUMB
)


def _thumb(name: str, size: tuple[int, int]) -> None:
    path = Path(settings.MEDIA_ROOT) / 'thumbs' / name[0] / name
    Image.new('RGB', size, (40, 90, 160)).save(path)


@pytest.fixture
def old_video_entry(monkeypatch) -> Entry:
    _thumb(OLD_THUMB, (200, 150))
    _thumb(NEW_THUMB, (320, 180))
    monkeypatch.setattr(
        'glifestream.apis.youtube.media.save_image',
        lambda url, **kwargs: '[GLS-THUMBS]/%s' % NEW_THUMB,
    )
    service = Service.objects.create(name='YouTube', api='youtube', public=True)
    return Entry.objects.create(
        service=service,
        guid='tag:youtube.com,2008:video:e2eVideo01',
        title='An Old Video',
        link='http://www.youtube.com/watch?v=e2eVideo01',
        content=OLD_CONTENT,
    )


def test_review_apply_and_revert_an_upgrade(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    stub_external_requests,
    old_video_entry: Entry,
):
    entry = old_video_entry
    ensure_admin_session()

    page.goto(f'{app_base_url}/settings/upgrades')
    row = page.locator('tr[data-upgrader="youtube"]')
    expect(row.locator('.pending')).to_have_text('1')
    row.get_by_role('link', name='Review').click()

    compare = page.locator('#stream.upgrade-compare')
    expect(compare.locator('> article')).to_have_count(2)
    expect(compare.locator('> article').first.locator('img')).to_have_attribute(
        'src', f'/media/thumbs/a/{OLD_THUMB}'
    )
    expect(compare.locator('> article').last.locator('img')).to_have_attribute(
        'src', f'/media/thumbs/b/{NEW_THUMB}'
    )
    expect(compare.locator('table.vc')).to_have_count(1)

    # Both sides play the video, as the stream would.
    embed = 'https://www.youtube.com/embed/e2eVideo01?autoplay=1&rel=0'
    for side in (compare.locator('> article').first, compare.locator('> article').last):
        side.locator('.play-video').click()
        expect(side.locator('div.player.video.youtube iframe')).to_have_attribute(
            'src', embed
        )
        side.locator('.play-video').click()
        expect(side.locator('div.player')).to_have_count(0)

    page.locator('details.upgrade-diff summary').click()
    expect(page.locator('.upgrade-diff .ins').first).to_be_visible()

    page.get_by_role('button', name='Apply B').click()
    expect(page.locator('.upgrade-messages .done')).to_contain_text(
        f'Applied to entry #{entry.pk}.'
    )
    expect(page.get_by_text('All YouTube entries are up to date.')).to_be_visible()

    page.goto(f'{app_base_url}/entry/{entry.pk}')
    player = page.locator('#stream [data-id="youtube-e2eVideo01"].play-video')
    expect(player.locator('img')).to_have_attribute(
        'src', f'/media/thumbs/b/{NEW_THUMB}'
    )
    expect(page.locator('#stream table.vc')).to_have_count(0)

    page.go_back()
    page.locator('.upgrade-messages .done').get_by_role('button', name='Revert').click()
    expect(page.locator('.upgrade-messages')).to_contain_text('Reverted.')
    expect(page.locator('#stream.upgrade-compare > article')).to_have_count(2)

    entry.refresh_from_db()
    assert entry.content == OLD_CONTENT
    assert entry.link == 'http://www.youtube.com/watch?v=e2eVideo01'
