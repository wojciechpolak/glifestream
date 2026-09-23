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

Characterization tests for the stream page behaviour of glifestream.js.

They pin what a user sees and what reaches the server, not how the script
does it, so they must keep passing unchanged while the script is rewritten.
Assert on DOM visible to the user, request payloads and database state; never
on jQuery internals or animation classes.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import Dialog, Locator, Page, Request, expect

from glifestream.stream.models import Entry, Favorite, Service

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def _article(page: Page, entry: Entry) -> Locator:
    return page.locator(f'#entry-{entry.pk}')


def _menu_action(page: Page, entry: Entry, control: str) -> None:
    """Open the entry's menu and click one of its controls."""
    article = _article(page, entry)
    article.locator('.entry-controls-switch').click()
    article.locator(f'.entry-controls .{control}').click()


def _is_api_post(cmd: str) -> Any:
    def _match(request: Request) -> bool:
        return request.method == 'POST' and request.url.endswith(f'/api/{cmd}')

    return _match


def _form(request: Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.post_data or '').items()}


def _csrf_cookie(page: Page) -> str:
    cookies = {c['name']: c['value'] for c in page.context.cookies()}
    return cookies['csrftoken']


def _record_dialogs(page: Page, *, accept: bool | list[bool] = True) -> list[str]:
    """Answer alert/confirm dialogs and return the list of their messages.

    `accept` is either one answer for every dialog or the answers in order.
    """
    messages: list[str] = []
    answers = list(accept) if isinstance(accept, list) else None

    def _handle(dialog: Dialog) -> None:
        messages.append(dialog.message)
        answer = answers.pop(0) if answers is not None else accept
        if answer:
            dialog.accept()
        else:
            dialog.dismiss()

    page.on('dialog', _handle)
    return messages


def _admin() -> User:
    return User.objects.get(username='admin')


# --- Entry menu -------------------------------------------------------------


def test_entry_menu_opens_and_closes_on_outside_click(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Menu Entry', 'Menu content')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    controls = _article(page, entry).locator('.entry-controls')
    expect(controls).to_be_hidden()

    _article(page, entry).locator('.entry-controls-switch').click()
    expect(controls).to_be_visible()
    expect(controls.locator('.favorite-control')).to_have_text('Favorite')
    expect(controls.locator('.hide-control')).to_be_visible()

    page.locator('#head h1').click()
    expect(controls).to_be_hidden()


def test_only_one_entry_menu_is_open_at_a_time(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    first = make_entry('First Menu Entry')
    second = make_entry('Second Menu Entry')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    # Open the lower menu first: an open menu drops down over the next entry.
    _article(page, second).locator('.entry-controls-switch').click()
    expect(_article(page, second).locator('.entry-controls')).to_be_visible()

    _article(page, first).locator('.entry-controls-switch').click()
    expect(_article(page, first).locator('.entry-controls')).to_be_visible()
    expect(_article(page, second).locator('.entry-controls')).to_be_hidden()


# --- Favorite ---------------------------------------------------------------


def test_favorite_and_unfavorite_entry(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Favorite Entry', 'Favorite content')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = _article(page, entry)
    expect(article.locator('span.favorite')).to_have_count(0)

    with page.expect_request(_is_api_post('favorite')) as request_info:
        _menu_action(page, entry, 'favorite-control')
    request = request_info.value
    assert _form(request) == {'entry': str(entry.pk)}
    assert request.headers['x-csrftoken'] == _csrf_cookie(page)

    expect(article.locator('span.favorite')).to_have_count(1)
    expect(article.locator('.favorite-control')).to_have_text('Unfavorite')
    assert Favorite.objects.filter(entry=entry, user=_admin()).exists()

    with page.expect_request(_is_api_post('unfavorite')) as request_info:
        _menu_action(page, entry, 'favorite-control')
    assert _form(request_info.value) == {'entry': str(entry.pk)}

    expect(article.locator('span.favorite')).to_have_count(0)
    expect(article.locator('.favorite-control')).to_have_text('Favorite')
    assert not Favorite.objects.filter(entry=entry).exists()


# --- Hide / Undo ------------------------------------------------------------


def test_hide_entry_and_undo(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Hidden Entry', 'Soon hidden')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = _article(page, entry)

    with page.expect_request(_is_api_post('hide')) as request_info:
        _menu_action(page, entry, 'hide-control')
    assert _form(request_info.value) == {'entry': str(entry.pk)}
    assert request_info.value.headers['x-csrftoken'] == _csrf_cookie(page)

    placeholder = page.locator(f'#hidden-{entry.pk}')
    expect(placeholder).to_contain_text('Entry hidden')
    expect(article).to_be_hidden()
    entry.refresh_from_db()
    assert entry.active is False

    with page.expect_request(_is_api_post('unhide')) as request_info:
        placeholder.get_by_role('link', name='Undo').click()
    assert _form(request_info.value) == {'entry': str(entry.pk)}

    expect(placeholder).to_have_count(0)
    expect(article).to_be_visible()
    entry.refresh_from_db()
    assert entry.active is True


def test_favorite_entry_cannot_be_hidden(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Favorite Hidden Entry')
    ensure_admin_session()
    Favorite.objects.create(user=_admin(), entry=entry)
    page.goto(f'{app_base_url}/')
    dialogs = _record_dialogs(page)
    hide_requests: list[Request] = []
    page.on(
        'request',
        lambda r: hide_requests.append(r) if _is_api_post('hide')(r) else None,
    )

    _menu_action(page, entry, 'hide-control')

    expect(_article(page, entry)).to_be_visible()
    assert dialogs == ['Unfavorite this entry before hiding it.']
    assert hide_requests == []
    entry.refresh_from_db()
    assert entry.active is True


# --- Expand content ---------------------------------------------------------


def test_title_only_entry_loads_content_once_and_toggles(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    titles = Service.objects.create(
        api='selfposts',
        name='Title Notes',
        cls='titles',
        display='title',
        home=True,
        active=True,
        public=False,
    )
    entry = make_entry('Title Only Entry', '<p>Expanded body text</p>', service=titles)
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = _article(page, entry)
    content = article.locator('div.entry-content')
    expect(content).to_be_hidden()

    getcontent: list[Request] = []
    page.on(
        'request',
        lambda r: getcontent.append(r) if _is_api_post('getcontent')(r) else None,
    )

    article.locator('a.expand-content').click()
    expect(content).to_be_visible()
    expect(content).to_contain_text('Expanded body text')
    assert len(getcontent) == 1
    assert _form(getcontent[0]) == {'entry': str(entry.pk)}

    article.locator('a.expand-content').click()
    expect(content).to_be_hidden()
    article.locator('a.expand-content').click()
    expect(content).to_be_visible()
    assert len(getcontent) == 1


# --- Errors -----------------------------------------------------------------


def test_failed_request_alerts_and_clears_spinner(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Error Entry')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    page.route('**/api/hide', lambda route: route.fulfill(status=500, body='boom'))
    dialogs = _record_dialogs(page)

    _menu_action(page, entry, 'hide-control')

    expect(page.locator('#spinner')).to_have_count(0)
    assert dialogs == ['Communication Error. Try again.']
    expect(_article(page, entry)).to_be_visible()
    expect(page.locator(f'#hidden-{entry.pk}')).to_have_count(0)


def test_spinner_shows_while_request_is_pending(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Spinner Entry')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    pending: list[Any] = []
    page.route('**/api/favorite', lambda route: pending.append(route))

    _menu_action(page, entry, 'favorite-control')
    expect(page.locator('#spinner')).to_have_count(1)

    page.wait_for_function('true')
    assert len(pending) == 1
    pending[0].fulfill(status=200, body='')
    expect(page.locator('#spinner')).to_have_count(0)
    expect(_article(page, entry).locator('span.favorite')).to_have_count(1)


# --- Editing ----------------------------------------------------------------


def _quill(page: Page) -> Locator:
    return page.locator('#status-editor .ql-editor')


def test_edit_entry_in_rich_editor_saves_content(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Rich Edit Entry', '<div>Original rich content</div>')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    expect(page.locator('#share .fieldset')).to_be_hidden()

    with page.expect_request(_is_api_post('getcontent')) as request_info:
        _menu_action(page, entry, 'edit-control')
    assert _form(request_info.value) == {'entry': str(entry.pk), 'raw': '1'}

    expect(page.locator('#share .fieldset')).to_be_visible()
    expect(_quill(page)).to_contain_text('Original rich content')
    expect(page.locator('#update')).to_be_visible()
    expect(page.locator('#post')).to_be_hidden()

    _quill(page).click()
    page.keyboard.press('End')
    page.keyboard.type(' plus edit')
    with page.expect_request(_is_api_post('putcontent')) as request_info:
        page.locator('#update').click()
    form = _form(request_info.value)
    assert form['entry'] == str(entry.pk)
    assert 'Original rich content plus edit' in form['content']

    expect(page.locator('#update')).to_be_enabled()
    expect(page.locator('#spinner')).to_have_count(0)
    entry.refresh_from_db()
    assert 'Original rich content plus edit' in entry.content


def test_raw_edit_replaces_entry_content(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Raw Edit Entry', '<p>Raw original</p>')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = _article(page, entry)
    editor = page.locator('#entry-editor')
    expect(editor).to_be_hidden()

    with page.expect_request(_is_api_post('getcontent')) as request_info:
        _menu_action(page, entry, 'editRaw-control')
    assert _form(request_info.value) == {'entry': str(entry.pk), 'raw': '1'}

    expect(article.locator('#entry-editor')).to_be_visible()
    expect(page.locator('#edited-content')).to_have_value('<p>Raw original</p>')

    page.locator('#edited-content').fill('<p>Raw <b>changed</b></p>')
    with page.expect_request(_is_api_post('putcontent')) as request_info:
        editor.locator('input[name=save]').click()
    assert _form(request_info.value) == {
        'entry': str(entry.pk),
        'content': '<p>Raw <b>changed</b></p>',
    }
    expect(article.locator('.entry-content b')).to_have_text('changed')
    entry.refresh_from_db()
    assert entry.content == '<p>Raw <b>changed</b></p>'

    editor.locator('input[name=cancel]').click()
    expect(editor).to_be_hidden()


# --- Composing selfposts ----------------------------------------------------


def _share_requests(page: Page) -> list[Request]:
    requests: list[Request] = []
    page.on(
        'request',
        lambda r: requests.append(r) if _is_api_post('share')(r) else None,
    )
    return requests


def _gsc_requests(page: Page) -> list[Request]:
    requests: list[Request] = []
    page.on(
        'request',
        lambda r: requests.append(r) if r.url.endswith('/api/gsc') else None,
    )
    return requests


def test_compose_and_post_selfpost(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    notes_service: Service,
    make_entry,
):
    make_entry('Existing Entry')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    gsc = _gsc_requests(page)
    share = page.locator('#share')
    expect(share).to_have_class(re.compile(r'\bshare-collapsed\b'))

    page.locator('#ashare').click()
    expect(share.locator('.fieldset')).to_be_visible()
    expect(share).not_to_have_class(re.compile(r'\bshare-collapsed\b'))
    expect(page.locator('#status-class option')).to_have_text(['notes'])
    expect(page.locator('#status-class')).to_have_value(str(notes_service.pk))
    expect(_quill(page)).to_be_focused()
    assert len(gsc) == 1

    page.keyboard.type('Hello from Playwright')
    with page.expect_request(_is_api_post('share')) as request_info:
        page.locator('#post').click()
    form = _form(request_info.value)
    assert form['sid'] == str(notes_service.pk)
    assert form['draft'] == '0'
    assert form['friends_only'] == '0'
    assert 'Hello from Playwright' in form['content']

    first = page.locator('#stream article.hentry').first
    expect(first).to_contain_text('Hello from Playwright')
    expect(share.locator('.fieldset')).to_be_hidden()
    expect(share).to_have_class(re.compile(r'\bshare-collapsed\b'))
    expect(page.locator('#post')).to_be_enabled()
    expect(_quill(page)).to_have_text('')
    assert Entry.objects.filter(
        content__contains='Hello from Playwright', draft=False
    ).exists()

    page.locator('#ashare').click()
    expect(share.locator('.fieldset')).to_be_visible()
    expect(page.locator('#status-class option')).to_have_count(1)
    assert len(gsc) == 1


def test_add_content_toggles_the_composer(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    fieldset = page.locator('#share .fieldset')

    page.locator('#ashare').click()
    expect(fieldset).to_be_visible()
    page.locator('#ashare').click()
    expect(fieldset).to_be_hidden()
    expect(page.locator('#share')).to_have_class(re.compile(r'\bshare-collapsed\b'))


def test_empty_selfpost_is_not_sent(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    sent = _share_requests(page)

    page.locator('#ashare').click()
    expect(_quill(page)).to_be_focused()
    page.keyboard.type('   ')
    page.locator('#post').click()

    expect(page.locator('#post')).to_be_enabled()
    expect(page.locator('#share .fieldset')).to_be_visible()
    page.wait_for_timeout(300)
    assert sent == []


def test_more_sharing_options_reveal_draft_and_files(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    page.locator('#ashare').click()
    options = page.locator('#more-sharing-options')
    expect(options).to_be_hidden()

    page.locator('#expand-sharing').click()
    expect(options).to_be_visible()
    expect(page.locator('#expand-sharing')).to_be_hidden()
    expect(page.locator('#draft')).to_be_visible()
    expect(page.locator('#friends-only')).to_be_visible()
    expect(page.locator('#gls-docs')).to_be_visible()


@pytest.mark.xfail(
    strict=True,
    reason='share() reads the checked attribute, not the checkbox state',
)
def test_draft_and_friends_only_checkboxes_are_sent(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    page.locator('#ashare').click()
    expect(_quill(page)).to_be_focused()
    page.keyboard.type('A draft for friends')
    page.locator('#expand-sharing').click()
    page.locator('#draft').check()
    page.locator('#friends-only').check()

    with page.expect_request(_is_api_post('share')) as request_info:
        page.locator('#post').click()
    form = _form(request_info.value)
    assert form['draft'] == '1'
    assert form['friends_only'] == '1'


def test_share_target_prefills_the_composer(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(
        f'{app_base_url}/share?title=Shared+title&text=Shared+text'
        '&url=https%3A%2F%2Fexample.test%2Fshared'
    )

    expect(page.locator('#share .fieldset')).to_be_visible()
    lines = _quill(page).locator('> *')
    expect(lines.nth(0)).to_have_text('Shared title')
    expect(lines.nth(1)).to_have_text('Shared text')
    expect(lines.nth(2)).to_have_text('https://example.test/shared')


# --- Share box and reshare --------------------------------------------------


def _share_link(page: Page, site: str) -> str:
    return (
        page.locator('#shareitbox .item a', has_text=site).get_attribute('href') or ''
    )


def test_share_box_lists_sites_with_encoded_links(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    long_title = 'Share this: ' + 'x' * 150
    entry = make_entry(long_title, 'Shared content')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    box = page.locator('#shareitbox')
    article = _article(page, entry)

    article.locator('a.shareit').click()
    expect(box).to_be_visible()
    expect(page.locator('#overlay')).to_be_visible()
    expect(box.get_by_role('link', name='Reshare it at your stream')).to_be_visible()

    bookmark = article.locator('a[rel=bookmark]').get_attribute('href')
    assert bookmark and bookmark.startswith(f'/entry/{entry.pk}')
    url = app_base_url + bookmark
    title = long_title[:137] + '...'
    expected = {
        'E-mail': 'mailto:?subject={URL}&body={TITLE}',
        'Twitter': 'https://twitter.com/?status={TITLE}:%20{URL}',
        'Facebook': 'https://www.facebook.com/sharer.php?u={URL}&t={TITLE}',
        'Reddit': 'https://reddit.com/submit?url={URL}&title={TITLE}',
    }
    encoded_url, encoded_title = page.evaluate(
        '([u, t]) => [encodeURIComponent(u), encodeURIComponent(t)]', [url, title]
    )
    for name, template in expected.items():
        link = box.locator('.item a', has_text=name)
        expect(link).to_have_attribute(
            'href',
            template.replace('{URL}', encoded_url).replace('{TITLE}', encoded_title),
        )
        expect(link).to_have_attribute('target', '_blank')

    page.keyboard.press('Escape')
    expect(box).to_be_hidden()
    expect(page.locator('#overlay')).to_have_count(0)

    article.locator('a.shareit').click()
    expect(box).to_be_visible()
    expect(box.locator('.item a', has_text='Reddit')).to_have_count(1)
    page.locator('#overlay').click(position={'x': 5, 'y': 5})
    expect(box).to_be_hidden()
    expect(page.locator('#overlay')).to_have_count(0)


@pytest.mark.xfail(
    strict=True,
    reason='shareit_entry takes the title from .html(), so entities stay escaped',
)
def test_share_box_title_is_plain_text(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Salt & Pepper')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    _article(page, entry).locator('a.shareit').click()
    href = _share_link(page, 'E-mail')
    assert href.endswith('&body=Salt%20%26%20Pepper')


def test_reshare_entry_as_me(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Reshared Entry', 'Worth resharing')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    before = Entry.objects.count()
    dialogs = _record_dialogs(page, accept=[True, False])

    _article(page, entry).locator('a.shareit').click()
    with page.expect_request(_is_api_post('reshare')) as request_info:
        page.get_by_role('link', name='Reshare it at your stream').click()
    assert _form(request_info.value) == {'entry': str(entry.pk), 'as_me': '1'}
    assert dialogs == [
        'You are about to re-share this entry at your stream. Confirm?',
        'Keep the original author?',
    ]

    expect(page.locator('#stream article', has_text='Worth resharing')).to_have_count(2)
    expect(page.locator('#shareitbox')).to_be_hidden()
    expect(page.locator('#overlay')).to_have_count(0)
    assert Entry.objects.count() == before + 1


def test_reshare_keeps_author_when_asked(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Author Entry', 'Keep my author')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    _record_dialogs(page, accept=[True, True])

    _article(page, entry).locator('a.shareit').click()
    with page.expect_request(_is_api_post('reshare')) as request_info:
        page.get_by_role('link', name='Reshare it at your stream').click()
    assert _form(request_info.value) == {'entry': str(entry.pk), 'as_me': '0'}


def test_reshare_can_be_cancelled(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Not Reshared Entry')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    before = Entry.objects.count()
    dialogs = _record_dialogs(page, accept=False)
    requests: list[Request] = []
    page.on(
        'request',
        lambda r: requests.append(r) if _is_api_post('reshare')(r) else None,
    )

    _article(page, entry).locator('a.shareit').click()
    page.get_by_role('link', name='Reshare it at your stream').click()

    assert dialogs == ['You are about to re-share this entry at your stream. Confirm?']
    expect(page.locator('#shareitbox')).to_be_visible()
    assert requests == []
    assert Entry.objects.count() == before


# --- Continuous reading -----------------------------------------------------

PIXEL = (
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQV'
    'R42mP8/x8AAusB9pQnUnYAAAAASUVORK5CYII='
)


def _titles(page: Page) -> list[str]:
    return page.locator('#stream article .entry-title').all_inner_texts()


def _next_link(page: Page) -> Locator:
    return page.locator('#stream nav a.next')


def test_older_entries_load_in_place_until_the_end(
    page: Page, app_base_url: str, ensure_admin_session, make_entry, settings
):
    settings.ENTRIES_ON_PAGE = 3
    for n in range(1, 7):
        content = ''
        if n == 5:
            content = (
                '<div class="thumbnails"><a href="https://www.youtube.com/watch?v=late5">'
                f'<img src="{PIXEL}" alt="late video" /></a></div>'
            )
        make_entry(f'Paged Entry {n}', content)
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    expect(page.locator('#stream article')).to_have_count(3)
    first_href = _next_link(page).get_attribute('href')
    assert first_href and 'start=' in first_href

    with page.expect_request(
        lambda r: 'format=html-pure' in r.url and r.method == 'GET'
    ) as request_info:
        _next_link(page).click()
    assert 'start=' in request_info.value.url
    expect(page.locator('#stream article')).to_have_count(6)
    assert page.url == f'{app_base_url}/'
    assert _titles(page) == [f'Paged Entry {n}' for n in range(1, 7)]
    second_href = _next_link(page).get_attribute('href')
    assert second_href and second_href != first_href and 'start=' in second_href

    # Entries loaded later get the same treatment as the first page.
    expect(page.locator('#youtube-late5.play-video .playbutton')).to_have_count(1)

    _next_link(page).click()
    expect(page.locator('#stream article')).to_have_count(7)
    assert _titles(page)[-1] == 'Seeded Private Entry'
    expect(_next_link(page)).to_have_count(0)


# --- Keyboard shortcuts -----------------------------------------------------


def _highlighted(page: Page) -> Locator:
    return page.locator('#stream article.entry-highlight')


def test_j_and_k_move_between_entries(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    first = make_entry('Key Entry One')
    second = make_entry('Key Entry Two')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    expect(_highlighted(page)).to_have_count(0)

    page.keyboard.press('j')
    expect(_highlighted(page)).to_have_id(f'entry-{first.pk}')
    page.keyboard.press('j')
    expect(_highlighted(page)).to_have_id(f'entry-{second.pk}')
    expect(_highlighted(page)).to_have_count(1)
    page.keyboard.press('k')
    expect(_highlighted(page)).to_have_id(f'entry-{first.pk}')

    page.keyboard.press('Control+j')
    page.keyboard.press('Alt+j')
    expect(_highlighted(page)).to_have_id(f'entry-{first.pk}')


def test_j_past_the_last_entry_loads_more(
    page: Page, app_base_url: str, ensure_admin_session, make_entry, settings
):
    settings.ENTRIES_ON_PAGE = 2
    make_entry('Key Page One')
    make_entry('Key Page Two')
    make_entry('Key Page Three')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    expect(page.locator('#stream article')).to_have_count(2)

    page.keyboard.press('j')
    page.keyboard.press('j')
    expect(_highlighted(page)).to_contain_text('Key Page Two')
    page.keyboard.press('j')
    expect(page.locator('#stream article')).to_have_count(4)

    page.keyboard.press('j')
    expect(_highlighted(page)).to_contain_text('Key Page Three')


def test_f_and_h_act_on_the_highlighted_entry(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Key Action Entry')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = _article(page, entry)

    page.keyboard.press('j')
    with page.expect_request(_is_api_post('favorite')) as request_info:
        page.keyboard.press('f')
    assert _form(request_info.value) == {'entry': str(entry.pk)}
    expect(article.locator('span.favorite')).to_have_count(1)
    with page.expect_request(_is_api_post('unfavorite')):
        page.keyboard.press('f')
    expect(article.locator('span.favorite')).to_have_count(0)

    with page.expect_request(_is_api_post('hide')):
        page.keyboard.press('h')
    expect(page.locator(f'#hidden-{entry.pk}')).to_be_visible()
    with page.expect_request(_is_api_post('unhide')):
        page.keyboard.press('h')
    expect(page.locator(f'#hidden-{entry.pk}')).to_have_count(0)
    expect(article).to_be_visible()


def test_a_opens_the_composer_and_typing_there_is_not_a_shortcut(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    make_entry('Composer Key Entry')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.keyboard.press('a')
    expect(page.locator('#share .fieldset')).to_be_visible()
    expect(_quill(page)).to_be_focused()
    page.keyboard.type('jjj a')
    expect(_highlighted(page)).to_have_count(0)
    expect(page.locator('#share .fieldset')).to_be_visible()
    expect(_quill(page)).to_contain_text('jjj a')


def test_typing_in_search_is_not_a_shortcut(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    make_entry('Search Key Entry')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator('input[name=s]').click()
    page.keyboard.type('jja')
    expect(page.locator('input[name=s]')).to_have_value('jja')
    expect(_highlighted(page)).to_have_count(0)
    expect(page.locator('#share .fieldset')).to_be_hidden()

    page.locator('#head h1').click()
    page.keyboard.press('j')
    expect(_highlighted(page)).to_have_count(1)


def test_enter_on_a_focused_link_span_activates_it(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator('#ashare').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#share .fieldset')).to_be_visible()


# --- Video and audio --------------------------------------------------------


def _thumb(href: str) -> str:
    return (
        f'<div class="thumbnails"><a href="{href}">'
        f'<img src="{PIXEL}" alt="thumb" /></a></div>'
    )


@pytest.mark.parametrize(
    ('href', 'wrapper_id', 'provider', 'embed_src'),
    [
        (
            'https://www.youtube.com/watch?v=abcXYZ123',
            'youtube-abcXYZ123',
            'youtube',
            'https://www.youtube.com/embed/abcXYZ123?autoplay=1&rel=0',
        ),
        (
            'http://www.youtube.com/watch?v=oldHttp1',
            'youtube-oldHttp1',
            'youtube',
            'https://www.youtube.com/embed/oldHttp1?autoplay=1&rel=0',
        ),
        (
            'https://vimeo.com/76979871',
            'vimeo-76979871',
            'vimeo',
            'https://player.vimeo.com/video/76979871?autoplay=1',
        ),
    ],
)
def test_video_thumbnail_plays_and_stops_embed(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    make_entry,
    stub_external_requests,
    href: str,
    wrapper_id: str,
    provider: str,
    embed_src: str,
):
    make_entry('Video Entry', _thumb(href))
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    wrapper = page.locator(f'#{wrapper_id}.play-video')
    expect(wrapper.locator('.playbutton')).to_have_count(1)
    player = page.locator(f'div.player.video.{provider}')

    wrapper.click()
    expect(player.locator('iframe')).to_have_attribute('src', embed_src)
    expect(wrapper.locator('.stopbutton')).to_have_count(1)
    expect(wrapper.locator('.playbutton')).to_have_count(0)

    wrapper.click()
    expect(player).to_have_count(0)
    expect(wrapper.locator('.playbutton')).to_have_count(1)


def test_mastodon_gifv_plays_inline_looped_and_muted(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    page.route('**/media/clip.mp4', lambda route: route.fulfill(status=404))
    make_entry(
        'Mastodon Video Entry',
        '<div data-id="mastodon-77" data-src="/media/clip.mp4"'
        f' data-poster="{PIXEL}" data-media-type="gifv"'
        ' data-width="640" data-height="360" class="play-video">'
        f'<a href="/media/clip.mp4" rel="nofollow"><img src="{PIXEL}" alt="clip" /></a>'
        '<div class="playbutton"></div></div>',
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    wrapper = page.locator('[data-id="mastodon-77"]')

    wrapper.click()
    player = page.locator('div.player.video.mastodon')
    expect(player).to_have_count(1)
    expect(player).to_have_attribute('style', re.compile(r'padding-bottom:\s*56\.25'))
    video = player.locator('video')
    props = video.evaluate(
        """v => ({src: v.src, poster: v.poster, loop: v.loop, muted: v.muted,
                 controls: v.controls, playsInline: v.playsInline})"""
    )
    assert props['src'].endswith('/media/clip.mp4')
    assert props['poster'] == PIXEL
    assert props['loop'] is True
    assert props['muted'] is True
    assert props['controls'] is True
    assert props['playsInline'] is True

    wrapper.click()
    expect(player).to_have_count(0)


def test_inline_video_toggles_on_repeated_clicks(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    page.route('**/media/inline.mp4', lambda route: route.fulfill(status=404))
    make_entry(
        'Inline Video Entry',
        '<span data-id="mastodon-88" data-src="/media/inline.mp4"'
        ' class="play-video video-inline">'
        '<a href="/media/inline.mp4">inline clip</a></span>',
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    wrapper = page.locator('[data-id="mastodon-88"]')
    player = page.locator('div.player.video.mastodon')

    wrapper.click()
    expect(player.locator('video')).to_have_count(1)
    wrapper.click()
    expect(player).to_have_count(0)
    wrapper.click()
    expect(player.locator('video')).to_have_count(1)
    assert page.url == f'{app_base_url}/'


@pytest.mark.parametrize('filename', ['song.mp3', 'song.ogg'])
def test_audio_file_link_plays_inline(
    page: Page, app_base_url: str, ensure_admin_session, make_entry, filename: str
):
    page.route(f'**/media/{filename}', lambda route: route.fulfill(status=404))
    make_entry(
        'Audio Entry',
        f'<div class="files"><a href="/media/{filename}">{filename}</a></div>',
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    trigger = page.locator('span.play-audio', has_text=filename)
    expect(trigger).to_have_attribute('title', 'Click and Listen')

    trigger.click()
    audio = page.locator('.files .player.audio audio')
    expect(audio).to_have_count(1)
    assert (audio.get_attribute('src') or '').endswith(f'/media/{filename}')
    assert page.url == f'{app_base_url}/'

    trigger.click()
    expect(page.locator('.player.audio')).to_have_count(0)


# --- Image lightbox ---------------------------------------------------------


def _lightbox_image(page: Page) -> Locator:
    """The image shown by the lightbox.

    The only selector here tied to the lightbox library (fancyBox 3). Update
    it, and nothing else, when the library is replaced.
    """
    return page.locator('.fancybox-slide--current img.fancybox-image')


def _lightbox(page: Page) -> Locator:
    """The lightbox container; see `_lightbox_image`."""
    return page.locator('.fancybox-container')


def _serve_images(page: Page) -> None:
    from glifestream.tests.e2e.conftest import MOCK_AVATAR_PNG

    page.route(
        re.compile(r'.*/media/gallery/.*\.jpg$'),
        lambda route: route.fulfill(
            status=200, body=MOCK_AVATAR_PNG, content_type='image/png'
        ),
    )


def _gallery(*names: str) -> str:
    links = ''.join(
        f'<a href="/media/gallery/{n}.jpg"><img src="{PIXEL}" alt="{n}" /></a>'
        for n in names
    )
    return f'<div class="thumbnails">{links}</div>'


def test_thumbnail_opens_lightbox_gallery_of_its_entry(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    _serve_images(page)
    make_entry('Gallery Entry', _gallery('one', 'two'))
    make_entry('Other Gallery Entry', _gallery('elsewhere'))
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator('a[href="/media/gallery/two.jpg"]').click()
    expect(_lightbox(page)).to_be_visible()
    expect(_lightbox_image(page)).to_have_attribute(
        'src', re.compile(r'/media/gallery/two\.jpg$')
    )
    assert page.url == f'{app_base_url}/'

    page.keyboard.press('ArrowRight')
    expect(_lightbox_image(page)).to_have_attribute(
        'src', re.compile(r'/media/gallery/one\.jpg$')
    )
    page.keyboard.press('ArrowRight')
    expect(_lightbox_image(page)).to_have_attribute(
        'src', re.compile(r'/media/gallery/two\.jpg$')
    )

    page.keyboard.press('Escape')
    expect(_lightbox(page)).to_have_count(0)


def test_single_thumbnail_opens_alone(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    _serve_images(page)
    make_entry('Single Image Entry', _gallery('solo'))
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator('a[href="/media/gallery/solo.jpg"]').click()
    expect(_lightbox_image(page)).to_have_attribute(
        'src', re.compile(r'/media/gallery/solo\.jpg$')
    )


# --- Maps -------------------------------------------------------------------

LAT = 52.2297
LNG = 21.0122


def _osm_bbox(lat: float, lng: float) -> str:
    import math

    angular = 10 / 6371
    lat_diff = angular * 180 / math.pi
    lng_diff = angular * 180 / (math.pi * math.cos(lat * math.pi / 180))
    return (
        f'{lng - lng_diff:.7f},{lat - lat_diff:.7f},'
        f'{lng + lng_diff:.7f},{lat + lat_diff:.7f}'
    )


def test_show_map_embeds_openstreetmap(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    make_entry,
    stub_external_requests,
):
    make_entry('Geo Entry', 'Somewhere', geolat=LAT, geolng=LNG)
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    link = page.locator('.geo a.show-map')
    lat, lng = '52.2297000000', '21.0122000000'
    expect(link.locator('.latitude')).to_have_text(lat)

    link.click()
    iframe = page.locator('.geo iframe')
    expect(iframe).to_have_attribute(
        'src',
        'https://www.openstreetmap.org/export/embed.html?layer=mapnik'
        f'&bbox={_osm_bbox(LAT, LNG)}&marker={lat},{lng}',
    )
    expect(
        page.locator('.geo a:not(.show-map)', has_text='View Larger Map')
    ).to_have_attribute(
        'href',
        f'https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=10/{lat}/{lng}',
    )
    expect(link).to_have_attribute(
        'href',
        f'https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=10/{lat}/{lng}',
    )
    expect(link).to_have_attribute('target', '_blank')
    assert page.url == f'{app_base_url}/'


def test_show_map_with_google_engine(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    make_entry,
    stub_external_requests,
    settings,
):
    settings.MAPS_ENGINE = 'google'
    make_entry('Google Geo Entry', 'Somewhere', geolat=LAT, geolng=LNG)
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    link = page.locator('.geo a.show-map')
    lat, lng = '52.2297000000', '21.0122000000'

    link.click()
    expect(page.locator('.geo img')).to_have_attribute(
        'src',
        'https://maps.googleapis.com/maps/api/staticmap?sensor=false&zoom=12'
        f'&size=175x120&markers={lat},{lng}',
    )
    expect(link).to_have_attribute('href', f'https://maps.google.com/?q={lat},{lng}')


def test_map_link_in_content_renders_on_load(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    make_entry,
    stub_external_requests,
):
    make_entry(
        'Inline Map Entry',
        '<p><a class="map" href="#"><span class="latitude">52.2297</span>'
        '<span class="longitude">21.0122</span></a></p>',
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    expect(page.locator('a.map iframe')).to_have_attribute(
        'src',
        'https://www.openstreetmap.org/export/embed.html?layer=mapnik'
        f'&bbox={_osm_bbox(LAT, LNG)}&marker=52.2297,21.0122',
    )
    expect(page.locator('a.map')).to_have_attribute('target', '_blank')


# --- Archive calendar -------------------------------------------------------


def test_archive_calendar_navigates_years(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    import datetime

    make_entry('Calendar Entry')  # June 2025; the seeded entry is January 2024.
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    calendar = page.locator('#calendar')
    months = calendar.locator('.month-cell')
    links = calendar.locator('a.month-item')

    expect(calendar.locator('.year')).to_have_text('2025')
    expect(months).to_have_count(12)
    expect(months.first).to_have_text('Jan')
    expect(months.last).to_have_text('Dec')
    expect(links).to_have_count(1)
    expect(links).to_have_attribute('href', '/2025/06/')
    expect(links).to_have_class(re.compile(r'\bview-month\b'))

    calendar.locator('a.prev').click()
    expect(calendar.locator('.year')).to_have_text('2024')
    expect(links).to_have_count(1)
    expect(links).to_have_attribute('href', '/2024/01/')
    expect(links).not_to_have_class(re.compile(r'\bview-month\b'))
    assert page.url == f'{app_base_url}/'

    this_year = datetime.date.today().year
    for year in range(2025, this_year + 1):
        calendar.locator('a.next').click()
        expect(calendar.locator('.year')).to_have_text(str(year))
    expect(calendar.locator('a.next')).to_have_count(0)
    expect(calendar.locator('.next-disabled')).to_have_count(1)

    for year in range(this_year - 1, 2023, -1):
        calendar.locator('a.prev').click()
        expect(calendar.locator('.year')).to_have_text(str(year))
    links.click()
    expect(page).to_have_url(f'{app_base_url}/2024/01/')


# --- Sidebar controls -------------------------------------------------------


def _cookie(page: Page, name: str) -> str | None:
    for cookie in page.context.cookies():
        if cookie['name'] == name:
            return cookie['value']
    return None


def test_change_theme_cycles_through_themes(
    page: Page, app_base_url: str, ensure_admin_session, reload_spy, settings
):
    settings.THEMES = ('default', 'dark', 'sepia')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    for expected, reloads in (('dark', 1), ('sepia', 2), ('default', 3)):
        page.locator('#change-theme').click()
        assert _cookie(page, 'gls-theme') == expected
        assert reload_spy() == reloads


def test_toggle_reblogs_flips_cookie(
    page: Page, app_base_url: str, ensure_admin_session, reload_spy
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator('#toggle-reblogs').click()
    assert _cookie(page, 'gls-reblogs') == '1'
    page.locator('#toggle-reblogs').click()
    assert _cookie(page, 'gls-reblogs') == '0'
    assert reload_spy() == 2


def test_list_selector_navigates_to_list(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator('div.lists select').select_option('seeded-list')
    expect(page).to_have_url(f'{app_base_url}/list/seeded-list/')


def test_empty_search_is_not_submitted(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    search = page.locator('input[name=s]')

    search.click()
    page.keyboard.press('Enter')
    page.locator('#search-submit').click()
    page.wait_for_timeout(300)
    assert page.url == f'{app_base_url}/'

    search.fill('Seeded')
    page.locator('#search-submit').click()
    expect(page).to_have_url(f'{app_base_url}/?s=Seeded')
    expect(page.locator('#stream article')).to_have_count(1)


def test_scroll_to_top_button(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    for n in range(12):
        make_entry(f'Long Page Entry {n}', '<p>' + 'Lorem ipsum. ' * 40 + '</p>')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    button = page.locator('.scroll-to-top')
    expect(button).to_be_hidden()

    page.mouse.wheel(0, 1500)
    expect(button).to_be_visible()
    button.click()
    page.wait_for_function('window.scrollY === 0')
    expect(button).to_be_hidden()


def test_web_share_is_offered_when_the_browser_supports_it(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Web Share Entry')
    page.add_init_script(
        """
        window.__shared = [];
        navigator.share = function(data) {
            window.__shared.push(data);
            return Promise.resolve();
        };
        """
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    article = _article(page, entry)
    bookmark = article.locator('a[rel=bookmark]').get_attribute('href')

    article.locator('a.shareit').click()
    page.locator('#shareitbox .item a', has_text='Web Share').click()
    shared = page.evaluate('window.__shared')
    assert shared == [{'title': 'Web Share Entry', 'url': app_base_url + str(bookmark)}]


# --- Pull to refresh --------------------------------------------------------


def test_cancelled_pull_to_refresh_resets(
    page: Page, app_base_url: str, ensure_admin_session, reload_spy
):
    ensure_admin_session()
    page.set_viewport_size({'width': 390, 'height': 680})
    page.goto(f'{app_base_url}/')

    state = page.evaluate(
        """
        () => {
            const target = document.getElementById('stream');
            const touch = (type, y) => {
                const event = new Event(type, {bubbles: true, cancelable: true});
                const points = [{clientX: 140, clientY: y}];
                Object.defineProperty(event, 'touches', {
                    value: type === 'touchcancel' ? [] : points
                });
                Object.defineProperty(event, 'changedTouches', {value: points});
                target.dispatchEvent(event);
            };
            touch('touchstart', 120);
            touch('touchmove', 310);
            const armed = document.body.classList.contains('pull-refresh-armed');
            touch('touchcancel', 310);
            return {
                armed: armed,
                classes: document.body.className,
                text: document.getElementById('pull-to-refresh').textContent.trim()
            };
        }
        """
    )
    assert state['armed'] is True
    assert 'pull-refresh' not in state['classes']
    assert state['text'] == 'Pull to refresh'
    assert reload_spy() == 0
