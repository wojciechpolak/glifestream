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

Waiting for a condition in the page, under its Content Security Policy.

Playwright's wait_for_function evaluates its predicate with eval, which the
policy blocks. page.evaluate compiles the function it is given over the
DevTools Protocol, outside the policy, so the predicate is written into that
function instead and checked on every animation frame, as Playwright does.
"""

from __future__ import annotations

import json

from playwright.sync_api import Page


def wait_for(page: Page, expression: str, *, timeout_ms: int = 30_000) -> None:
    """Waits until the JavaScript `expression` is truthy in the page."""
    page.evaluate(
        f"""
        () => new Promise((resolve, reject) => {{
            const until = performance.now() + {timeout_ms};
            const check = () => {{
                if ({expression}) {{
                    resolve(true);
                }} else if (performance.now() > until) {{
                    reject(new Error('Timed out waiting for ' + {json.dumps(expression)}));
                }} else {{
                    requestAnimationFrame(check);
                }}
            }};
            check();
        }})
        """
    )
