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

The Content Security Policy the site sends, for Django's CSP middleware.

Scripts run only from the static files, or from an inline script that carries
the request's nonce, `nonce="{{ csp_nonce }}"`: the pages themselves have no
inline script or event handler attribute. Entries show images, audio, video
and players from any site, so those stay open; inline styles stay allowed,
since the page script and its libraries set `style` attributes.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.utils.csp import CSP

CSP_MODES = ('enforce', 'report-only', 'off')


def _origin(url: str) -> list[str]:
    """The origin of an absolute URL, as a CSP source; none for a path."""
    parts = urlsplit(url)
    if not parts.netloc:
        return []
    return [f'{parts.scheme}://{parts.netloc}' if parts.scheme else parts.netloc]


def content_security_policy(static_url: str) -> dict[str, list[str]]:
    static = [CSP.SELF, *_origin(static_url)]
    return {
        'default-src': [CSP.SELF],
        'script-src': [*static, CSP.NONCE],
        'style-src': [*static, CSP.UNSAFE_INLINE],
        'font-src': [*static, 'data:'],
        'img-src': ['*', 'data:', 'blob:'],
        'media-src': ['*', 'data:', 'blob:'],
        'frame-src': ['*'],
        'connect-src': [CSP.SELF],
        'object-src': [CSP.NONE],
        'base-uri': [CSP.SELF],
    }


def csp_settings(
    mode: str, *, static_url: str
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """SECURE_CSP and SECURE_CSP_REPORT_ONLY for a CONTENT_SECURITY_POLICY mode."""
    mode = mode.strip().lower()
    if mode not in CSP_MODES:
        raise ValueError(
            f'CONTENT_SECURITY_POLICY must be one of {", ".join(CSP_MODES)}, '
            f'not {mode!r}.'
        )
    policy = content_security_policy(static_url)
    return (
        policy if mode == 'enforce' else {},
        policy if mode == 'report-only' else {},
    )
