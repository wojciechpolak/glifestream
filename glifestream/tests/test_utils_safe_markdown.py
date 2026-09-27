import pytest

from glifestream.utils import safe_markdown

BASE = 'https://github.com/me/app/'


def test_markdown_becomes_html():
    html = safe_markdown.render('Some **bold** and `code`.\n\n* one\n* two', BASE)

    assert '<strong>bold</strong>' in html
    assert '<code>code</code>' in html
    assert '<li>one</li>' in html


def test_headings_become_bold_paragraphs():
    html = safe_markdown.render('## [1.1.0](https://example.com/c) (2026-09-17)', BASE)

    assert html == (
        '<p><strong><a href="https://example.com/c" rel="nofollow">1.1.0</a>'
        ' (2026-09-17)</strong></p>'
    )


def test_raw_html_is_shown_as_text():
    html = safe_markdown.render(
        '<script>alert(1)</script>\n\nhi <img src=x onerror=alert(1)>', BASE
    )

    assert '<script' not in html and '<img' not in html
    assert '&lt;script&gt;' in html


@pytest.mark.parametrize(
    'url',
    [
        'javascript:alert(1)',
        'JavaScript:alert(1)',
        'data:text/html;base64,PHNjcmlwdD4=',
        'vbscript:msgbox(1)',
    ],
)
def test_unsafe_link_loses_its_target(url):
    html = safe_markdown.render('[x](%s)' % url, BASE)

    assert html == '<p><a>x</a></p>'


def test_relative_links_resolve_against_the_base():
    html = safe_markdown.render('[c](compare/v1...v2) [m](mailto:me@example.com)', BASE)

    assert 'href="https://github.com/me/app/compare/v1...v2"' in html
    assert 'href="mailto:me@example.com"' in html


def test_images_become_links():
    html = safe_markdown.render(
        '![shot](https://i.example/a.png) [![badge](https://i.example/b.svg)]'
        '(https://ci.example)',
        BASE,
    )

    assert '<img' not in html
    assert '<a href="https://i.example/a.png" rel="nofollow">shot</a>' in html
    # A linked image leaves its text inside the one link.
    assert '<a href="https://ci.example" rel="nofollow"><span>badge</span></a>' in html


def test_code_blocks_and_tables():
    html = safe_markdown.render(
        "```js\nlet a = '<b>';\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |", BASE
    )

    assert "let a = '&lt;b&gt;';" in html
    assert '<td>1</td>' in html


def test_excerpt_keeps_short_text_whole():
    assert safe_markdown.excerpt('short', 100) == ('short', False)


def test_excerpt_cuts_at_a_line_and_closes_an_open_fence():
    text = 'intro\n```\ncode\n' + 'x' * 100

    kept, cut = safe_markdown.excerpt(text, 20)

    assert cut
    assert kept == 'intro\n```\ncode\n```'


def test_excerpt_cuts_a_single_long_line():
    kept, cut = safe_markdown.excerpt('y' * 100, 10)

    assert (kept, cut) == ('y' * 10, True)
