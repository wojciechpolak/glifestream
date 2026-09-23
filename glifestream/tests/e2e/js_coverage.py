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

Function coverage of the page script across the E2E run.

Enabled with GLS_E2E_JS_COVERAGE=1. Each page starts V8 precise coverage over
the Chrome DevTools Protocol. The counts are taken before every main-frame
navigation and on teardown, mapped back to the script and summed over the
session. The summary lists every function literal in the script with how often
the tests called it, and where it is in frontend/src, so a rewrite can check
that the part it replaces is exercised first.

`npm run build` writes the script to js/dist/glifestream.js with a source map
beside it, and django-pipeline serves it concatenated into js/main.<hash>.js.
So the built file is located inside that bundle, V8 offsets are shifted by
where it starts, and the map leads from a function in the built file to its
line in the sources. V8 reports a function's start at its `function` keyword,
which is what the static scan below records too.
"""

from __future__ import annotations

import json
import re
import string
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from playwright.sync_api import BrowserContext, CDPSession, Page, Request

ROOT = Path(__file__).parents[3]
BUILT = ROOT / 'glifestream' / 'static' / 'js' / 'dist' / 'glifestream.js'
BUNDLE_PATH = re.compile(r'/js/main(\.[0-9a-f]+)?\.js$')


@dataclass(frozen=True)
class JsFunction:
    offset: int
    where: str
    label: str


_BASE64 = {
    c: i
    for i, c in enumerate(
        string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
    )
}


def _vlq(segment: str) -> list[int]:
    """The numbers of one source map segment."""
    values, value, shift = [], 0, 0
    for char in segment:
        digit = _BASE64[char]
        value += (digit & 31) << shift
        if digit & 32:
            shift += 5
            continue
        values.append(-(value >> 1) if value & 1 else value >> 1)
        value, shift = 0, 0
    return values


@dataclass(frozen=True)
class SourceMap:
    """Where each generated line and column came from in the sources."""

    sources: list[Path]
    contents: list[str]
    # Per generated line: (column, source index, source line), by column.
    lines: list[list[tuple[int, int, int]]]

    @classmethod
    def read(cls, path: Path) -> SourceMap:
        data = json.loads(path.read_text())
        lines: list[list[tuple[int, int, int]]] = []
        source = source_line = 0
        for encoded in data['mappings'].split(';'):
            column = 0
            segments = []
            for fields in map(_vlq, filter(None, encoded.split(','))):
                column += fields[0]
                if len(fields) >= 4:
                    source += fields[1]
                    source_line += fields[2]
                    segments.append((column, source, source_line))
            lines.append(segments)
        return cls(
            [(path.parent / name).resolve() for name in data['sources']],
            data.get('sourcesContent') or [],
            lines,
        )

    def original(self, line: int, column: int) -> tuple[int, int] | None:
        """(source index, source line), both from 0, of a generated position."""
        found = None
        for segment_column, source, source_line in (
            self.lines[line] if line < len(self.lines) else ()
        ):
            if segment_column > column and found is not None:
                break
            found = (source, source_line)
        return found


def scan_functions(built: str, source_map: SourceMap) -> list[JsFunction]:
    """Every `function` literal in the built script, labelled from its source."""
    functions = []
    # A literal is the keyword followed by an optional name and its parameter
    # list; this skips the word inside strings such as `typeof x == 'function'`.
    for match in re.finditer(r"(?<!['\"])\bfunction\b(?=\s*[\w$]*\s*\()", built):
        offset = match.start()
        line = built.count('\n', 0, offset)
        column = offset - (built.rfind('\n', 0, offset) + 1)
        origin = source_map.original(line, column)
        if origin is None:
            continue
        source, source_line = origin
        text = source_map.contents[source].splitlines()[source_line].strip()
        declared = re.search(r'\bfunction\s+([\w$]+)', text)
        label = declared.group(1) if declared else text[:72]
        where = source_map.sources[source].relative_to(ROOT)
        functions.append(JsFunction(offset, f'{where}:{source_line + 1}', label))
    return functions


@dataclass
class JsCoverage:
    output_dir: Path
    source: str = field(default_factory=lambda: BUILT.read_text())
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
        functions = scan_functions(
            self.source, SourceMap.read(BUILT.with_name(BUILT.name + '.map'))
        )
        rows = [(fn, self.counts.get(fn.offset, 0)) for fn in functions]
        called = sum(1 for _, count in rows if count)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / 'functions.json').write_text(
            json.dumps(
                [
                    {'where': fn.where, 'label': fn.label, 'calls': count}
                    for fn, count in rows
                ],
                indent=2,
            )
        )
        lines = [
            f'{BUILT.name}: {called} of {len(rows)} functions called '
            f'in {self.snapshots} snapshots.',
            '',
            'Never called:',
            *(f'  {fn.where}  {fn.label}' for fn, count in rows if not count),
        ]
        summary = self.output_dir / 'summary.txt'
        summary.write_text('\n'.join(lines) + '\n')
        return called, len(rows), summary
