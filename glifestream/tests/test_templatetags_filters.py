import datetime
import pytest
from django.utils.safestring import SafeString
from glifestream.stream.templatetags.gls_filters import (
    gls_date,
    gls_udate,
    gls_hdate,
    gls_slugify,
    encode_json,
    fix_ampersands_filter,
    gls_urlizetrunc,
    gls_link,
    gls_title,
    gls_content,
)

UTC = datetime.timezone.utc


@pytest.fixture(autouse=True)
def system_tz():
    import os
    import time

    old_tz = os.environ.get('TZ')
    os.environ['TZ'] = 'UTC'
    time.tzset()
    yield
    if old_tz:
        os.environ['TZ'] = old_tz
    else:
        del os.environ['TZ']
    time.tzset()


@pytest.mark.parametrize(
    'input_date,expected_suffix',
    [
        (datetime.datetime.now(UTC) - datetime.timedelta(minutes=5), 'minutes ago'),
        (datetime.datetime.now(UTC) - datetime.timedelta(hours=2), 'hours ago'),
        (datetime.datetime.now(UTC) - datetime.timedelta(hours=25), 'Yesterday'),
    ],
)
def test_gls_date_relative(input_date, expected_suffix):
    # gls_date uses get_relative_time for recent dates
    res = gls_date(input_date)
    assert expected_suffix in res


def test_gls_date_absolute():
    # Dates older than 7 days return formatted date
    old_date = datetime.datetime(2023, 1, 1, 10, 0, tzinfo=UTC)
    res = gls_date(old_date)
    assert '2023' in res


def test_gls_udate():
    dt = datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC)
    # gls_udate returns int timestamp
    res = gls_udate(dt)
    assert isinstance(res, int)
    assert res > 0


def test_gls_hdate():
    dt = datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC)
    res = gls_hdate(dt)
    assert '2023-11-01T' in res
    assert res.endswith('Z')


def test_gls_slugify_filter():
    assert gls_slugify('Hello World') == 'hello-world'
    assert gls_slugify('Ends with-') == 'ends-with'
    assert gls_slugify('Part-http') == 'part'


def test_encode_json():
    data = {'a': 1, 'b': 'c'}
    res = encode_json(data)
    assert isinstance(res, SafeString)
    assert '"a": 1' in res


def test_fix_ampersands_filter():
    assert fix_ampersands_filter('') == ''
    assert fix_ampersands_filter('&') == '&amp;'
    assert fix_ampersands_filter('a&b') == 'a&amp;b'
    assert fix_ampersands_filter('a & b') == 'a &amp; b'
    assert fix_ampersands_filter('a & b &amp;') == 'a &amp; b &amp;'
    assert fix_ampersands_filter('a &amp; b') == 'a &amp; b'
    assert fix_ampersands_filter('Fast&Fun;') == 'Fast&amp;Fun;'


def test_gls_urlizetrunc():
    text = 'Check http://verylongurl.com/something'
    res = gls_urlizetrunc(text, 10)
    assert 'rel="nofollow"' in res
    assert 'http://...' in res


@pytest.mark.django_db
def test_gls_link_and_title(service):
    from glifestream.stream.models import Entry

    e = Entry(
        service=service,
        title='Test',
        guid='t1',
        date_published=datetime.datetime.now(UTC),
    )
    e.save()

    # gls_link
    link = gls_link(None, e)
    assert '?class=feed' in link

    # gls_title
    title = gls_title(None, e)
    assert title == 'Test'

    # Empty title fallback to date
    e.title = ''
    title = gls_title(None, e)
    assert '202' in title  # Should contain current decade


@pytest.mark.django_db
def test_gls_content_friends_only(service):
    from glifestream.stream.models import Entry

    e = Entry(
        service=service,
        title='Test',
        guid='t1',
        friends_only=True,
        content='Private',
        date_published=datetime.datetime.now(UTC),
    )
    e.save()

    content = gls_content(None, e)
    assert 'friends-only-entry' in content
    assert 'Private' not in content
