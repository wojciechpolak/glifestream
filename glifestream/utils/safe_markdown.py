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
"""

import xml.etree.ElementTree as etree
from urllib.parse import urljoin, urlsplit

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

SAFE_URL_SCHEMES = ('http', 'https', 'mailto')
HEADINGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')


def render(text: str, base_url: str) -> str:
    """HTML for Markdown someone else wrote, safe to put in a page.

    Raw HTML in `text` is shown as text. Links resolve against `base_url`
    and keep only the http, https and mailto schemes. Images become links,
    and headings become bold paragraphs, so the result sits inside an entry.
    """
    md = markdown.Markdown(
        extensions=['fenced_code', 'tables', 'sane_lists', _SafeExtension(base_url)]
    )
    md.preprocessors.deregister('html_block')
    md.inlinePatterns.deregister('html')
    return md.convert(text)


def excerpt(text: str, limit: int) -> tuple[str, bool]:
    """The first lines of `text` that fit in `limit` characters.

    Returns them and whether anything was left out. A code fence the cut
    leaves open is closed.
    """
    if len(text) <= limit:
        return text, False
    lines: list[str] = []
    size = 0
    for line in text.splitlines():
        if lines and size + len(line) > limit:
            break
        lines.append(line[:limit])
        size += len(line) + 1
    kept = '\n'.join(lines)
    if kept.count('```') % 2:
        kept += '\n```'
    return kept, True


def _safe_url(url: str, base_url: str) -> str | None:
    absolute = urljoin(base_url, url.strip())
    if urlsplit(absolute).scheme.lower() in SAFE_URL_SCHEMES:
        return absolute
    return None


class _SafeTreeprocessor(Treeprocessor):
    def __init__(self, md: markdown.Markdown, base_url: str) -> None:
        super().__init__(md)
        self.base_url = base_url

    def run(self, root: etree.Element) -> None:
        in_link = {
            child for a in root.iter('a') for child in a.iter() if child is not a
        }
        for el in list(root.iter()):
            if el.tag in HEADINGS:
                _bold_paragraph(el)
            elif el.tag == 'img':
                src = el.get('src', '')
                text = el.get('alt') or src
                el.attrib.clear()
                el.text = text
                # An image inside a link keeps only its text.
                if el in in_link:
                    el.tag = 'span'
                else:
                    el.tag = 'a'
                    el.set('href', src)
            href = el.get('href')
            if href is not None:
                safe = _safe_url(href, self.base_url)
                if safe:
                    el.set('href', safe)
                    el.set('rel', 'nofollow')
                else:
                    del el.attrib['href']


class _SafeExtension(Extension):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # After the inline patterns (20), so it sees every link and image.
        md.treeprocessors.register(_SafeTreeprocessor(md, self.base_url), 'gls_safe', 5)


def _bold_paragraph(el: etree.Element) -> None:
    strong = etree.Element('strong')
    strong.text = el.text
    for child in list(el):
        el.remove(child)
        strong.append(child)
    el.text = None
    el.attrib.clear()
    el.tag = 'p'
    el.append(strong)
