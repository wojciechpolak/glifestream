from glifestream.utils.html import bytes_to_human, strip_entities, strip_script, urlize


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
