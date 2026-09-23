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

Function coverage of glifestream.js across the E2E run.

Enabled with GLS_E2E_JS_COVERAGE=1. Each page starts V8 precise coverage over
the Chrome DevTools Protocol. The counts are taken before every main-frame
navigation and on teardown, mapped back to glifestream.js and summed over the
session. The summary lists every function
literal in the file with how often the tests called it, so a rewrite can check
that the part it replaces is exercised first.

django-pipeline serves glifestream.js concatenated into js/main.<hash>.js, so
the file is located inside that bundle and V8 offsets are shifted by where it
starts. V8 reports a function's start at its `function` keyword, which is what
the static scan below records too.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from playwright.sync_api import BrowserContext, CDPSession, Page, Request

SOURCE = Path(__file__).parents[2] / 'static' / 'js' / 'glifestream.js'
BUNDLE_PATH = re.compile(r'/js/main(\.[0-9a-f]+)?\.js$')


@dataclass(frozen=True)
class JsFunction:
    offset: int
    line: int
    label: str


def scan_functions(source: str) -> list[JsFunction]:
    """Every `function` literal in the source, named where the code names it."""
    functions = []
    # A literal is the keyword followed by an optional name and its parameter
    # list; this skips the word inside strings such as `typeof x == 'function'`.
    for match in re.finditer(r"(?<!['\"])\bfunction\b(?=\s*[\w$]*\s*\()", source):
        offset = match.start()
        line_start = source.rfind('\n', 0, offset) + 1
        line_end = source.find('\n', offset)
        declared = re.match(r'function\s+([\w$]+)', source[offset:])
        if declared:
            label = declared.group(1)
        else:
            label = source[line_start:line_end].strip()[:72]
        functions.append(JsFunction(offset, source.count('\n', 0, offset) + 1, label))
    return functions


@dataclass
class JsCoverage:
    output_dir: Path
    source: str = field(default_factory=lambda: SOURCE.read_text())
    counts: Counter[int] = field(default_factory=Counter)
    snapshots: int = 0

    def watch(self, context: BrowserContext, page: Page) -> CDPSession:
        """Start counting on the page; pass the session to `collect` at the end."""
        cdp = context.new_cdp_session(page)
        cdp.send('Profiler.enable')
        cdp.send(
            'Profiler.startPreciseCoverage', {'callCount': True, 'detailed': False}
        )

        # A navigation can drop the old document's counts, so take them first.
        # Navigating to about:blank sends no request and still loses them.
        def _before_navigation(request: Request) -> None:
            if request.is_navigation_request() and request.frame == page.main_frame:
                self.collect(cdp)

        page.on('request', _before_navigation)
        return cdp

    def collect(self, cdp: CDPSession) -> None:
        result = cdp.send('Profiler.takePreciseCoverage')
        self.snapshots += 1
        for script in result['result']:
            url = script['url']
            if not BUNDLE_PATH.search(urlsplit(url).path):
                continue
            base = self._source_offset_in(url)
            if base < 0:
                continue
            for function in script['functions']:
                whole = function['ranges'][0]
                offset = whole['startOffset'] - base
                if 0 <= offset < len(self.source):
                    self.counts[offset] += whole['count']

    def _source_offset_in(self, url: str) -> int:
        path = urlsplit(url).path
        static_url = urlsplit(settings.STATIC_URL).path
        bundle = Path(settings.STATIC_ROOT) / path.removeprefix(static_url)
        try:
            return bundle.read_text().find(self.source)
        except OSError:
            return -1

    def report(self) -> tuple[int, int, Path]:
        """Write the summary files; return (called, total, summary path)."""
        functions = scan_functions(self.source)
        rows = [(fn, self.counts.get(fn.offset, 0)) for fn in functions]
        called = sum(1 for _, count in rows if count)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / 'functions.json').write_text(
            json.dumps(
                [
                    {'line': fn.line, 'label': fn.label, 'calls': count}
                    for fn, count in rows
                ],
                indent=2,
            )
        )
        lines = [
            f'glifestream.js: {called} of {len(rows)} functions called '
            f'in {self.snapshots} snapshots.',
            '',
            'Never called:',
            *(f'  {fn.line:5d}  {fn.label}' for fn, count in rows if not count),
        ]
        summary = self.output_dir / 'summary.txt'
        summary.write_text('\n'.join(lines) + '\n')
        return called, len(rows), summary
