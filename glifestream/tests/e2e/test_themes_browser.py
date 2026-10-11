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

The bundled themes built on themes/_kit/, light and dark, at every width:
they load nothing from elsewhere, keep their text legible, never scroll
sideways, and keep what the page script counts on working.
"""

from __future__ import annotations

import datetime
from typing import Literal

import pytest
from django.utils import timezone
from playwright.sync_api import FloatRect, Locator, Page, expect

from glifestream.settings_themes import BUNDLED_THEMES
from glifestream.stream.models import Entry, Service

pytestmark = pytest.mark.e2e

KIT_THEMES = tuple(name for name in BUNDLED_THEMES if name != 'default')
Scheme = Literal['light', 'dark']
SCHEMES: tuple[Scheme, ...] = ('light', 'dark')
WIDTHS = (320, 375, 768, 1024, 1440)

# The contrast of two colours, each resolved by the browser and read back
# off a canvas, whatever notation the theme wrote it in.
CONTRAST_JS = """
([fg, bg]) => {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  const resolve = (value) => {
    const el = document.createElement('i');
    el.style.color = value;
    document.body.append(el);
    const color = getComputedStyle(el).color;
    el.remove();
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, 1, 1);
    return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3);
  };
  const luminance = (rgb) => {
    const [r, g, b] = rgb.map((v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const a = luminance(resolve(fg));
  const b = luminance(resolve(bg));
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
"""

# Text of every kind on what it is set on.
TEXT_PAIRS = (
    ('var(--kit-ink)', 'var(--kit-paper)'),
    ('var(--kit-ink)', 'var(--kit-surface)'),
    ('var(--kit-ink-soft)', 'var(--kit-paper)'),
    ('var(--kit-ink-muted)', 'var(--kit-paper)'),
    ('var(--kit-ink-muted)', 'var(--kit-surface)'),
    ('var(--kit-link)', 'var(--kit-paper)'),
    ('var(--kit-link)', 'var(--kit-surface)'),
    ('var(--kit-danger)', 'var(--kit-paper)'),
)

LONG_TEXT = ''.join(
    f'<p>Paragraph {i}: a line long enough to wrap, and then another one, '
    'so that the entry runs past the lines it folds to.</p>'
    for i in range(40)
)


@pytest.fixture
def themed_stream(settings, seeded_e2e_state):
    """The bundled themes on offer, and a long public entry to fold."""
    settings.THEMES = BUNDLED_THEMES
    settings.DEFAULT_THEME = ''
    settings.FOLD_LINES = 10
    service = Service.objects.create(
        api='selfposts', name='Themed', public=True, display='both'
    )
    return Entry.objects.create(
        service=service,
        title='A long entry',
        content=LONG_TEXT,
        guid='themes-long-entry',
        link='https://example.org/long',
        date_published=timezone.now() - datetime.timedelta(days=1),
    )


def _use_theme(page: Page, app_base_url: str, theme: str, scheme: Scheme) -> list[str]:
    """Picks `theme` in `scheme`; the list fills with requests to elsewhere."""
    page.context.add_cookies(
        [{'name': 'gls-theme', 'value': theme, 'url': app_base_url}]
    )
    page.emulate_media(color_scheme=scheme)
    elsewhere: list[str] = []
    page.on(
        'request',
        lambda request: (
            None
            if request.url.startswith((app_base_url, 'data:', 'blob:'))
            else elsewhere.append(request.url)
        ),
    )
    return elsewhere


def _sideways_overflow(page: Page) -> list[int]:
    """The widths of WIDTHS at which the page scrolls sideways."""
    overflowing = []
    for width in WIDTHS:
        page.set_viewport_size({'width': width, 'height': 900})
        if page.evaluate('document.documentElement.scrollWidth > innerWidth'):
            overflowing.append(width)
    return overflowing


def _assert_in_reach(page: Page, items: Locator, container: str) -> None:
    """Each of `items` is what a click on its middle lands on, inside
    `container`: shown is not enough, a clip-path or an overflow can hide it
    and let the click go through to the page."""
    for item in items.all():
        box = item.bounding_box()
        assert box is not None
        assert page.evaluate(
            '([x, y, container]) =>'
            ' !!document.elementFromPoint(x, y)?.closest(container)',
            [box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, container],
        ), item.inner_text()


@pytest.mark.parametrize('scheme', SCHEMES)
@pytest.mark.parametrize('theme', KIT_THEMES)
def test_theme_fits_every_width_from_its_own_files(
    page: Page,
    app_base_url: str,
    themed_stream,
    ensure_admin_session,
    theme: str,
    scheme: Scheme,
):
    elsewhere = _use_theme(page, app_base_url, theme, scheme)

    page.goto(f'{app_base_url}/login')
    assert page.locator(f'link[href*="themes/{theme}/style"]').count() == 1
    assert page.evaluate('document.body.className') == f'style-{theme}'
    assert _sideways_overflow(page) == []

    ensure_admin_session()
    for path in ('/', f'/entry/{themed_stream.id}', '/settings/services'):
        page.set_viewport_size({'width': 1440, 'height': 900})
        page.goto(f'{app_base_url}{path}')
        assert _sideways_overflow(page) == [], path

    assert elsewhere == []


@pytest.mark.parametrize('scheme', SCHEMES)
@pytest.mark.parametrize('theme', KIT_THEMES)
def test_theme_text_is_legible(
    page: Page, app_base_url: str, themed_stream, theme: str, scheme: Scheme
):
    _use_theme(page, app_base_url, theme, scheme)
    page.goto(f'{app_base_url}/public/')

    low = {
        f'{fg} on {bg}': round(ratio, 2)
        for fg, bg in TEXT_PAIRS
        if (ratio := page.evaluate(CONTRAST_JS, [fg, bg])) < 4.5
    }
    assert low == {}


@pytest.mark.parametrize('theme', KIT_THEMES)
def test_theme_keeps_the_page_script_working(
    page: Page,
    app_base_url: str,
    themed_stream,
    ensure_admin_session,
    theme: str,
):
    _use_theme(page, app_base_url, theme, 'light')
    ensure_admin_session()

    # Wide: the top bar shows its links, and a long entry folds.
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto(f'{app_base_url}/')
    expect(page.locator('#navtop-toggle')).to_be_hidden()
    expect(page.locator('#navtop a[href$="/public/"]')).to_be_visible()
    content = page.locator(f'#entry-{themed_stream.id} .entry-content')
    expect(content).to_have_class('entry-content folded')
    page.locator(f'#entry-{themed_stream.id} .show-more').click()
    expect(content).not_to_have_class('entry-content folded')

    # The entry's menu opens by its switch.
    page.locator(f'#entry-{themed_stream.id} .entry-controls-switch').click()
    expect(page.locator(f'#entry-{themed_stream.id} .entry-controls')).to_be_visible()

    # The list of themes opens over its switch, every one of them in reach.
    page.locator('#change-theme').scroll_into_view_if_needed()
    page.locator('#change-theme').click()
    themes = page.locator('#theme-menu [data-theme]')
    expect(themes).to_have_count(len(BUNDLED_THEMES))
    _assert_in_reach(page, themes, '#theme-menu')

    # Narrower: the links fold into the menu button's panel.
    page.set_viewport_size({'width': 800, 'height': 900})
    page.goto(f'{app_base_url}/')
    expect(page.locator('#navtop .navtop-menu')).to_be_hidden()
    page.locator('#navtop-toggle').click()
    expect(page.locator('#navtop .navtop-menu')).to_be_visible()
    # Shown is not enough: a clip-path on the top bar once hid the menu
    # while it was open, and a click on it went through to the page.
    _assert_in_reach(page, page.locator('#navtop .navtop-menu a'), '#navtop-menu')

    # A phone: the sidebar is a drawer its handle opens.
    page.set_viewport_size({'width': 375, 'height': 800})
    page.goto(f'{app_base_url}/')
    expect(page.locator('#sidebar-toggle')).to_be_visible()
    expect(page.locator('#calendar')).to_be_hidden()
    page.locator('#sidebar-toggle').click()
    expect(page.locator('#sidebar')).to_have_class('expanded')
    expect(page.locator('#calendar')).to_be_visible()
    page.locator('#change-theme').scroll_into_view_if_needed()
    page.locator('#change-theme').click()
    themes = page.locator('#theme-menu [data-theme]')
    expect(themes).to_have_count(len(BUNDLED_THEMES))
    _assert_in_reach(page, themes, '#theme-menu')


@pytest.mark.parametrize('theme', BUNDLED_THEMES)
def test_sidebar_taller_than_the_window_scrolls_into_view(
    page: Page, app_base_url: str, themed_stream, ensure_admin_session, theme: str
):
    """The themes pin the sidebar; one taller than the window, by its bottom."""
    # Well under the sidebar's height, whatever fonts the system draws it in:
    # in the VRT image the phosphor sidebar is under 600px tall.
    window_height = 480
    _use_theme(page, app_base_url, theme, 'light')
    ensure_admin_session()
    page.set_viewport_size({'width': 1280, 'height': window_height})
    page.goto(f'{app_base_url}/')

    sidebar_height = page.evaluate(
        "document.getElementById('sidebar').getBoundingClientRect().height"
    )
    assert sidebar_height > window_height
    page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
    assert (
        page.evaluate("getComputedStyle(document.getElementById('sidebar')).position")
        == 'sticky'
    )
    foot = page.locator('#sidebar-foot').bounding_box()
    assert foot is not None
    assert foot['y'] + foot['height'] <= window_height


@pytest.mark.parametrize('scheme', SCHEMES)
@pytest.mark.parametrize('theme', KIT_THEMES)
def test_theme_shows_keyboard_focus_in_the_top_bar(
    page: Page, app_base_url: str, theme: str, scheme: Scheme
):
    """A link in the bar looks different focused: a clip-path that cuts a
    segment's arrow once cut its focus ring away too."""
    _use_theme(page, app_base_url, theme, scheme)
    page.set_viewport_size({'width': 1280, 'height': 800})
    page.goto(f'{app_base_url}/login')
    for selector in ('#head h1 a', '#navtop > a'):
        link = page.locator(selector)
        box = link.bounding_box()
        assert box is not None
        clip: FloatRect = {
            'x': max(0, box['x'] - 6),
            'y': max(0, box['y'] - 6),
            'width': box['width'] + 12,
            'height': box['height'] + 12,
        }
        before = page.screenshot(clip=clip, animations='disabled')
        link.focus()
        assert link.evaluate('el => el.matches(":focus-visible")'), selector
        after = page.screenshot(clip=clip, animations='disabled')
        link.blur()
        assert before != after, selector
