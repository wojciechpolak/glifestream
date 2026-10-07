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

Videos in the composer's editor: shown as the post shows them, kept when
an entry is edited, and a pasted address shown as its player at once.

The live server runs in this process, so the thumbnail is stubbed where
the server would download it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from PIL import Image
from playwright.sync_api import Page, expect

from glifestream.stream.models import Entry, Service

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

OLD_THUMB = 'a0e2e0000000000000000000000000000000old1.jpg'
NEW_THUMB = 'b0e2e0000000000000000000000000000000new1.webp'
OLD_POST = (
    '<p>Before the video</p>\n'
    '<table class="vc"><tr><td><div id="youtube-e2eVideo02" class="play-video">'
    '<a href="https://www.youtube.com/watch?v=e2eVideo02" rel="nofollow">'
    '<img src="[GLS-THUMBS]/%s" width="200" height="150" alt="YouTube Video" />'
    '</a><div class="playbutton"></div></div></td></tr></table>' % OLD_THUMB
)


def _thumb(name: str, size: tuple[int, int]) -> None:
    path = Path(settings.MEDIA_ROOT) / 'thumbs' / name[0] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', size, (40, 90, 160)).save(path)


@pytest.fixture
def new_thumbnail(monkeypatch) -> None:
    _thumb(OLD_THUMB, (200, 150))
    _thumb(NEW_THUMB, (320, 180))
    monkeypatch.setattr(
        'glifestream.filters.players.media.save_image',
        lambda url, **kwargs: '[GLS-THUMBS]/%s' % NEW_THUMB,
    )


def _editor_player(page: Page):
    return page.locator('#status-editor .editor-player')


def test_editing_a_post_shows_and_keeps_its_video(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    stub_external_requests,
    notes_service: Service,
    make_entry,
    new_thumbnail,
):
    Service.objects.filter(pk=notes_service.pk).update(public=True)
    entry = make_entry('A post with a video', OLD_POST)
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = page.locator(f'#entry-{entry.pk}')

    article.locator('.entry-controls-switch').click()
    article.locator('.entry-controls .edit-control').click()

    # The thumbnail the stream shows, not a link with its alt text.
    player = _editor_player(page)
    expect(player.locator('img')).to_have_attribute(
        'src', f'/media/thumbs/a/{OLD_THUMB}'
    )
    expect(player).to_contain_text('https://www.youtube.com/watch?v=e2eVideo02')
    expect(page.locator('#status-editor .ProseMirror')).to_contain_text(
        'Before the video'
    )
    # Under the editor, the entry as it will look once saved.
    preview = page.locator('#stream > article.entry-preview')
    expect(preview).to_contain_text('Before the video')
    expect(preview.locator('[data-id="youtube-e2eVideo02"] img')).to_have_attribute(
        'src', f'/media/thumbs/b/{NEW_THUMB}'
    )

    page.locator('#update').click()

    # The entry shows what was saved: the player with a thumbnail of its own.
    saved = article.locator('.entry-content [data-id="youtube-e2eVideo02"] img')
    expect(saved).to_have_attribute('src', f'/media/thumbs/b/{NEW_THUMB}')
    expect(article.locator('table.vc')).to_have_count(0)
    entry.refresh_from_db()
    assert 'class="play-video"' in entry.content
    assert '[GLS-THUMBS]/%s' % NEW_THUMB in entry.content


def test_a_pasted_video_address_is_a_player_before_it_is_posted(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    stub_external_requests,
    notes_service: Service,
    new_thumbnail,
):
    Service.objects.filter(pk=notes_service.pk).update(public=True)
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    page.locator('#ashare').click()
    editor = page.locator('#status-editor .ProseMirror')
    editor.click()
    editor.evaluate(
        """(el) => {
            const data = new DataTransfer();
            data.setData('text/plain', 'https://youtu.be/e2ePaste01');
            el.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: data, bubbles: true, cancelable: true,
            }));
        }"""
    )

    expect(_editor_player(page).locator('img')).to_have_attribute(
        'src', 'https://i.ytimg.com/vi/e2ePaste01/mqdefault.jpg'
    )
    # The editor's player has the stream's play button, and is only selected.
    _editor_player(page).locator('.play-video .playbutton').click()
    expect(page.locator('#share div.player')).to_have_count(0)

    # The preview shows the post as it will be, and plays its video.
    preview = page.locator('#stream > article.entry-preview')
    expect(preview.locator('.entry-preview-label')).to_have_text('Preview')
    preview.locator('.play-video').click()
    expect(preview.locator('div.player.video.youtube iframe')).to_have_attribute(
        'src', 'https://www.youtube.com/embed/e2ePaste01?autoplay=1&rel=0'
    )
    editor.click()
    page.keyboard.press('ControlOrMeta+End')
    page.keyboard.type('Worth a watch')
    expect(preview).to_contain_text('Worth a watch')

    page.locator('#post').click()

    expect(page.locator('#stream > article.entry-preview')).to_have_count(0)
    first = page.locator('#stream article.hentry').first
    expect(first.locator('[data-id="youtube-e2ePaste01"] img')).to_have_attribute(
        'src', f'/media/thumbs/b/{NEW_THUMB}'
    )
    entry = Entry.objects.get(content__contains='youtube-e2ePaste01')
    assert 'i.ytimg.com' not in entry.content


def test_the_class_of_an_imported_entry_is_locked_and_looks_it(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    stub_external_requests,
    make_entry,
):
    feed = Service.objects.create(name='A Feed', api='feed', url='http://feed.test/')
    entry = make_entry('From a feed', '<p>Imported</p>')
    Entry.objects.filter(pk=entry.pk).update(service=feed)
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = page.locator(f'#entry-{entry.pk}')

    article.locator('.entry-controls-switch').click()
    article.locator('.entry-controls .edit-control').click()

    select = page.locator('#status-class')
    expect(select).to_be_disabled()
    # Its own class, as its icon shows it, which no post has.
    expect(select.locator('option:checked')).to_have_text('feed')
    expect(select).to_have_attribute(
        'title', 'An imported entry keeps the class of its service.'
    )
    expect(select).to_have_css('opacity', '0.55')
    expect(select).to_have_css('cursor', 'not-allowed')

    # A new post may have any class again.
    page.locator('#ashare').click()
    page.locator('#ashare').click()
    expect(select).to_be_enabled()
    expect(select).to_have_attribute('title', '')
    expect(select.locator('option', has_text='feed')).to_have_count(0)


def test_editing_keeps_and_saves_the_checkboxes_of_an_entry(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    stub_external_requests,
    make_entry,
):
    entry = make_entry('For friends', '<div>Hello</div>', friends_only=True)
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = page.locator(f'#entry-{entry.pk}')

    article.locator('.entry-controls-switch').click()
    article.locator('.entry-controls .edit-control').click()

    friends = page.locator('#friends-only')
    expect(friends).to_be_visible()
    expect(friends).to_be_checked()
    expect(page.locator('#draft')).not_to_be_checked()

    # The preview shows the lock, as the stream shows it to the owner.
    lock = page.locator('#stream > article.entry-preview .friends-only-lock')
    expect(lock).to_have_count(1)

    friends.uncheck()
    expect(lock).to_have_count(0)
    page.locator('#draft').check()
    page.locator('#update').click()
    expect(page.locator('#update')).to_be_enabled()
    expect(page.locator(f'#entry-{entry.pk} .entry-content')).to_contain_text('Hello')

    entry.refresh_from_db()
    assert (entry.friends_only, entry.draft) == (False, True)

    # A new post starts with neither.
    page.locator('#ashare').click()
    page.locator('#ashare').click()
    expect(page.locator('#draft')).not_to_be_checked()


def test_the_html_source_is_published_with_the_post(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    stub_external_requests,
    notes_service: Service,
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    page.locator('#ashare').click()
    editor = page.locator('#status-editor .ProseMirror')
    editor.click()
    page.keyboard.type('Typed in the editor')

    page.get_by_role('button', name='HTML source').click()
    source = page.locator('#status-editor textarea.editor-source')
    expect(source).to_have_value('<div>Typed in the editor</div>')
    expect(editor).to_be_hidden()
    expect(page.get_by_role('button', name='Bold')).to_be_disabled()

    source.fill('<div>Written as <strong>HTML</strong></div>')
    preview = page.locator('#stream > article.entry-preview')
    expect(preview.locator('strong')).to_have_text('HTML')

    # The source has no saving of its own: the post publishes it.
    page.locator('#post').click()
    first = page.locator('#stream article.hentry').first
    expect(first.locator('.entry-content strong')).to_have_text('HTML')
    expect(source).to_be_hidden()
    expect(editor).to_be_visible()
    entry = Entry.objects.get(content__contains='Written as')
    assert '<strong>HTML</strong>' in entry.content
