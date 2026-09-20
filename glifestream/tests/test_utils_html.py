from django.utils.safestring import mark_safe

from glifestream.utils.html import (
    _resolve_link,
    _split_punctuation,
    bytes_to_human,
    strip_entities,
    strip_script,
    urlize,
)


def test_bytes_to_human():
    assert bytes_to_human(512) == '512 B'
    assert bytes_to_human(1024) == '1.00 kB'
    assert bytes_to_human(1024 * 1024) == '1.00 MB'
    assert bytes_to_human(1024 * 1024 * 1024) == '1.00 GB'
    assert bytes_to_human(2048, precision=1) == '2.0 kB'


def test_strip_entities():
    assert strip_entities('Hello &amp; world') == 'Hello  world'
    assert strip_entities('Test &#123; value') == 'Test  value'


def test_strip_script():
    html = '<div><script>alert("hi")</script><p>Hello</p></div>'
    # strip_script uses BeautifulSoup if available
    stripped = strip_script(html)
    assert '<script>' not in stripped
    assert 'Hello' in stripped


def test_urlize():
    assert 'href="http://example.com"' in urlize('Check http://example.com')
    assert 'href="mailto:test@example.com"' in urlize('Email test@example.com')
    assert 'rel="nofollow"' in urlize('http://example.com', nofollow=True)


def test_bytes_to_human_caps_out_at_gigabytes():
    assert bytes_to_human(1024**5) == '1024.00 GB'


def test_split_punctuation_peels_a_trailing_stop():
    assert _split_punctuation('http://example.com.') == (
        '',
        'http://example.com',
        '.',
    )


def test_split_punctuation_peels_several_trailing_marks():
    assert _split_punctuation('http://example.com.)') == (
        '',
        'http://example.com',
        '.)',
    )


def test_split_punctuation_peels_a_matching_wrapper():
    assert _split_punctuation('(http://example.com)') == (
        '(',
        'http://example.com',
        ')',
    )


def test_split_punctuation_keeps_a_balanced_closing_paren_in_the_url():
    assert _split_punctuation('http://ex.com/a_(b)') == (
        '',
        'http://ex.com/a_(b)',
        '',
    )


def test_split_punctuation_takes_the_semicolon_before_the_entity():
    """A semicolon is trailing punctuation, so `&gt;` never matches as a wrapper."""
    assert _split_punctuation('&lt;http://example.com&gt;') == (
        '&lt;',
        'http://example.com&gt',
        ';',
    )


def test_split_punctuation_leaves_a_plain_word_alone():
    assert _split_punctuation('example') == ('', 'example', '')


def test_resolve_link_handles_an_absolute_url():
    url, attr, skip = _resolve_link('https://example.com/a b', False)

    assert url == 'https://example.com/a%20b'
    assert (attr, skip) == ('', False)


def test_resolve_link_adds_a_scheme_to_a_bare_host():
    assert _resolve_link('www.example.org', True) == (
        'http://www.example.org',
        ' rel="nofollow"',
        False,
    )


def test_resolve_link_accepts_a_bare_gtld_host():
    url, _attr, _skip = _resolve_link('example.com', False)

    assert url == 'http://example.com'


def test_resolve_link_never_marks_an_email_nofollow():
    assert _resolve_link('test@example.com', True) == (
        'mailto:test@example.com',
        '',
        False,
    )


def test_resolve_link_punts_on_an_email_domain_it_cannot_encode():
    url, _attr, skip = _resolve_link('bob@' + 'x' * 70 + '.com', False)

    assert url is None
    assert skip is True


def test_resolve_link_leaves_an_ordinary_word_unlinked():
    assert _resolve_link('not.a.match.here', False) == (None, '', False)


def test_urlize_trims_a_long_url_in_the_link_text():
    html = urlize('http://example.com/a/very/long/path', trim_url_limit=20)

    assert 'href="http://example.com/a/very/long/path"' in html
    assert '>http://example.co...<' in html


def test_urlize_escapes_the_surrounding_text_when_asked():
    assert urlize('tea & http://x.com', autoescape=True) == (
        'tea &amp; <a href="http://x.com">http://x.com</a>'
    )


def test_urlize_leaves_safe_input_unescaped():
    assert urlize(mark_safe('tea & biscuits'), autoescape=True) == 'tea & biscuits'


def test_urlize_escapes_the_lead_and_trail_around_a_link():
    assert urlize('(http://x.com) & more', autoescape=True) == (
        '(<a href="http://x.com">http://x.com</a>) &amp; more'
    )


def test_urlize_passes_an_unencodable_email_through_untouched():
    address = 'bob@' + 'x' * 70 + '.com'

    assert urlize('write to %s & wait' % address, autoescape=True) == (
        'write to %s &amp; wait' % address
    )
