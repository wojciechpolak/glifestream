import pytest
import datetime
from unittest.mock import patch, MagicMock

import feedparser

from glifestream.apis.webfeed import WebfeedService
from glifestream.stream.models import Entry
from glifestream.utils import httpclient

UTC = datetime.timezone.utc


@pytest.fixture
def mock_feed():
    class AttrDict(dict):
        def __getattr__(self, name):
            if name in self:
                return self[name]
            # Avoid returning MagicMock for common feed attributes that should be None/empty
            if name in ['image', 'author_detail', 'updated_parsed', 'published_parsed']:
                raise AttributeError(name)
            return MagicMock()

        def __contains__(self, k):
            return super().__contains__(k)

    feed = MagicMock()
    feed.feed = AttrDict(link='http://example.com', author_detail={})
    feed.get.side_effect = lambda k, d='': {'etag': 'etag-123'}.get(k, d)
    feed.entries = []
    feed.etag = 'etag-123'
    feed.modified = 'Wed, 01 Nov 2023 12:00:00 GMT'
    feed.bozo = False
    return feed


@pytest.mark.django_db
def test_webfeed_fetch_basic(service, mock_feed):
    class AttrDict(dict):
        def __getattr__(self, name):
            if name in self:
                return self[name]
            if name in ['content', 'updated_parsed', 'published_parsed', 'links']:
                raise AttributeError(name)
            return MagicMock()

    entry_data = AttrDict(
        id='guid-1',
        link='http://example.com/1',
        title='Test Title',
        summary='Test Summary',
        published_parsed=(2023, 11, 1, 12, 0, 0, 2, 305, 0),
        links=[],
    )
    mock_feed.entries = [entry_data]

    with patch('glifestream.apis.webfeed.feedparser.parse', return_value=mock_feed):
        with patch('glifestream.apis.webfeed.httpclient') as mock_http:
            with patch('glifestream.apis.webfeed.media') as mock_media:
                mock_media.mrss_init.return_value = {'content': []}
                mock_media.mrss_gen_json.return_value = '{}'
                mock_media.save_image.return_value = ''

                mock_response = MagicMock()
                mock_response.headers = {'etag': 'etag-123'}
                mock_http.get_feed.return_value = httpclient.BodyResponse(
                    response=mock_response,
                    body=b'empty',
                )
                mock_http.gen_auth.return_value = {}

                api = WebfeedService(service)
                api.run()

                # Verify Service was updated
                service.refresh_from_db()
                assert service.etag == 'etag-123'

                # Verify Entry was created
                e = Entry.objects.get(guid='guid-1')
                assert e.title == 'Test Title'


@pytest.mark.django_db
def test_webfeed_payload(service, mock_feed):
    class AttrDict(dict):
        def __getattr__(self, name):
            if name in self:
                return self[name]
            if name in ['content', 'updated_parsed', 'published_parsed', 'links']:
                raise AttributeError(name)
            return MagicMock()

    mock_feed.entries = [AttrDict(id='p-1', title='Payload', summary='Sub', links=[])]

    with patch('glifestream.apis.webfeed.feedparser.parse', return_value=mock_feed):
        with patch('glifestream.apis.webfeed.media') as mock_media:
            mock_media.mrss_init.return_value = {'content': []}
            mock_media.mrss_gen_json.return_value = '{}'

            api = WebfeedService(service)
            api.payload = '<xml>fake</xml>'
            api.run()

            assert Entry.objects.filter(guid='p-1').exists()


@pytest.mark.django_db
def test_webfeed_bozo(service):
    # Test handling of malformed feed
    mock_feed = MagicMock()
    mock_feed.bozo = True
    mock_feed.bozo_exception = Exception('Malformed')

    with patch('glifestream.apis.webfeed.feedparser.parse', return_value=mock_feed):
        api = WebfeedService(service)
        api.payload = 'bad xml'
        with pytest.raises(httpclient.FetchError) as excinfo:
            api.run()

    assert excinfo.value.category == 'parse_error'
    assert Entry.objects.count() == 0


@pytest.mark.django_db
def test_webfeed_fetch_http_error_propagates(service):
    service.api = 'webfeed'
    service.save()
    api = WebfeedService(service)

    with (
        patch(
            'glifestream.apis.webfeed.httpclient.get_feed',
            side_effect=httpclient.build_fetch_error(
                category='remote_5xx',
                detail='HTTP 503 Service Unavailable from http://example.com/feed',
                retryable=True,
                status_code=503,
                url='http://example.com/feed',
            ),
        ),
        pytest.raises(httpclient.FetchError) as excinfo,
    ):
        api.run()

    assert excinfo.value.category == 'remote_5xx'


@pytest.mark.django_db
def test_webfeed_fetch_rejects_oversized_feed(service):
    service.api = 'webfeed'
    service.save()
    api = WebfeedService(service)

    with (
        patch(
            'glifestream.apis.webfeed.httpclient.get_feed',
            side_effect=httpclient.build_fetch_error(
                category='invalid_response',
                detail='Feed response from http://example.com/feed exceeds 10 bytes while streaming.',
                retryable=False,
                url='http://example.com/feed',
            ),
        ),
        pytest.raises(httpclient.FetchError) as excinfo,
    ):
        api.run()

    assert excinfo.value.category == 'invalid_response'


@pytest.mark.django_db
def test_webfeed_fetch_rejects_html_without_alternate_feed(service):
    service.api = 'webfeed'
    service.save()
    api = WebfeedService(service)

    with (
        patch(
            'glifestream.apis.webfeed.httpclient.get_feed',
            side_effect=httpclient.build_fetch_error(
                category='invalid_response',
                detail='HTML feed discovery response from http://example.com/feed did not expose an alternate feed link.',
                retryable=False,
                url='http://example.com/feed',
            ),
        ),
        pytest.raises(httpclient.FetchError) as excinfo,
    ):
        api.run()

    assert excinfo.value.category == 'invalid_response'


@pytest.mark.django_db
def test_webfeed_media_content(service, mock_feed):
    class AttrDict(dict):
        def __getattr__(self, name):
            if name in self:
                return self[name]
            if name in ['content', 'updated_parsed', 'published_parsed', 'links']:
                raise AttributeError(name)
            return MagicMock()

    entry_data = AttrDict(
        id='m-1',
        title='Media',
        summary='Content',
        media_content=[{'url': 'http://img.com', 'medium': 'image'}],
        links=[],
    )
    mock_feed.entries = [entry_data]

    with patch('glifestream.apis.webfeed.feedparser.parse', return_value=mock_feed):
        with patch('glifestream.apis.webfeed.media') as mock_media:
            mock_media.mrss_init.return_value = {'content': []}
            mock_media.mrss_gen_json.return_value = '{"content": "..."}'

            api = WebfeedService(service)
            api.payload = '...'
            api.run()

            e = Entry.objects.get(guid='m-1')

            api = WebfeedService(service)
            api.payload = '...'
            api.run()

            e = Entry.objects.get(guid='m-1')
            assert 'content' in e.mblob


# The helpers below drive `process` through real feedparser output rather than
# hand-built stand-ins, so the `x in entry` / `entry.x` duality is the real one.


def build_feed(items: str, *, channel_extra: str = '') -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:georss="http://www.georss.org/georss" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#" '
        'xmlns:atom="http://www.w3.org/2005/Atom">'
        '<channel><title>Feed</title><link>http://example.com</link>'
        '%s%s</channel></rss>' % (channel_extra, items)
    )


@pytest.fixture
def webfeed(service):
    service.api = 'webfeed'
    service.save()
    return WebfeedService(service)


def run_process(api, xml: str):
    api.fp = feedparser.parse(xml)
    api.process(api.fp.entries)


@pytest.mark.django_db
def test_process_maps_the_core_entry_fields(webfeed):
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>A Title</title>'
            '<link>http://example.com/1</link>'
            '<description>Some body</description>'
            '<pubDate>Wed, 01 Nov 2023 12:00:00 GMT</pubDate></item>'
        ),
    )

    entry = Entry.objects.get()
    assert entry.guid == 'g-1'
    assert entry.title == 'A Title'
    assert entry.link == 'http://example.com/1'
    assert 'Some body' in entry.content
    assert entry.date_published == datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC)


@pytest.mark.django_db
def test_process_falls_back_to_the_link_when_the_feed_has_no_guid(webfeed):
    run_process(
        webfeed,
        build_feed('<item><title>T</title><link>http://example.com/9</link></item>'),
    )

    assert Entry.objects.get().guid == 'http://example.com/9'


@pytest.mark.django_db
def test_process_prefers_the_entrys_own_author(webfeed):
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
            '<author>bob@example.com (Bob)</author></item>'
        ),
    )

    entry = Entry.objects.get()
    assert entry.author_name == 'Bob'
    assert entry.author_email == 'bob@example.com'


@pytest.mark.django_db
def test_process_falls_back_to_the_feed_level_author(webfeed):
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link></item>',
            channel_extra=(
                '<atom:author><atom:name>Feed Owner</atom:name>'
                '<atom:email>owner@example.com</atom:email>'
                '<atom:uri>http://example.com/owner</atom:uri></atom:author>'
            ),
        ),
    )

    entry = Entry.objects.get()
    assert entry.author_name == 'Feed Owner'
    assert entry.author_email == 'owner@example.com'
    assert entry.author_uri == 'http://example.com/owner'


@pytest.mark.django_db
def test_process_reads_a_dublin_core_creator(webfeed):
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
            '<dc:creator>Carol</dc:creator></item>'
        ),
    )

    assert Entry.objects.get().author_name == 'Carol'


@pytest.mark.django_db
def test_process_uses_the_updated_stamp_when_there_is_no_published_one(webfeed):
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
            '<atom:updated>2023-11-02T09:00:00Z</atom:updated></item>'
        ),
    )

    entry = Entry.objects.get()
    assert entry.date_published == datetime.datetime(2023, 11, 2, 9, 0, tzinfo=UTC)
    assert entry.date_updated == datetime.datetime(2023, 11, 2, 9, 0, tzinfo=UTC)


@pytest.mark.django_db
def test_process_reads_a_wgs84_position(webfeed):
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
            '<geo:lat>52.23</geo:lat><geo:long>21.01</geo:long></item>'
        ),
    )

    entry = Entry.objects.get()
    assert (float(entry.geolat), float(entry.geolng)) == (52.23, 21.01)


def test_apply_geo_still_understands_a_flat_georss_point():
    """Current feedparser normalizes georss:point into `where`; older ones did not."""
    entry = Entry()

    WebfeedService._apply_geo(entry, {'georss_point': '52.23 21.01'})

    assert (entry.geolat, entry.geolng) == ('52.23', '21.01')


@pytest.mark.django_db
def test_process_saves_an_image_link_from_the_entry(webfeed):
    xml = build_feed(
        '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
        '<atom:link rel="photo" href="http://e/photo.jpg" /></item>'
    )

    with patch(
        'glifestream.apis.webfeed.media.save_image', side_effect=lambda url, **kw: url
    ):
        run_process(webfeed, xml)

    assert Entry.objects.get().link_image == 'http://e/photo.jpg'


@pytest.mark.django_db
def test_process_prefers_the_feeds_own_image(webfeed):
    xml = build_feed(
        '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
        '<atom:link rel="image" href="http://e/entry.jpg" /></item>',
        channel_extra=(
            '<image><url>http://e/feed.png</url><title>Feed</title>'
            '<link>http://example.com</link></image>'
        ),
    )

    with patch(
        'glifestream.apis.webfeed.media.save_image', side_effect=lambda url, **kw: url
    ):
        run_process(webfeed, xml)

    assert Entry.objects.get().link_image == 'http://e/feed.png'


@pytest.mark.django_db
def test_process_leaves_link_image_alone_when_nothing_matches(webfeed):
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link></item>'
        ),
    )

    assert Entry.objects.get().link_image == ''


@pytest.mark.django_db
def test_process_strips_script_tags_from_the_body(webfeed):
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
            '<description>&lt;p&gt;ok&lt;/p&gt;'
            '&lt;script&gt;alert(1)&lt;/script&gt;</description></item>'
        ),
    )

    assert 'alert(1)' not in Entry.objects.get().content


@pytest.mark.django_db
def test_process_skips_an_entry_that_has_not_been_updated(webfeed):
    xml = build_feed(
        '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
        '<atom:updated>2023-11-02T09:00:00Z</atom:updated></item>'
    )
    run_process(webfeed, xml)
    Entry.objects.update(title='Edited by hand')

    run_process(webfeed, xml)

    assert Entry.objects.get().title == 'Edited by hand'


@pytest.mark.django_db
def test_force_overwrite_rewrites_an_unchanged_entry(webfeed):
    xml = build_feed(
        '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
        '<atom:updated>2023-11-02T09:00:00Z</atom:updated></item>'
    )
    run_process(webfeed, xml)
    Entry.objects.update(title='Edited by hand')

    webfeed.force_overwrite = True
    run_process(webfeed, xml)

    assert Entry.objects.get().title == 'T'


@pytest.mark.django_db
def test_process_never_touches_a_protected_entry(webfeed):
    xml = build_feed(
        '<item><guid>g-1</guid><title>T</title><link>http://e/1</link></item>'
    )
    run_process(webfeed, xml)
    Entry.objects.update(protected=True, title='Hands off')

    webfeed.force_overwrite = True
    run_process(webfeed, xml)

    assert Entry.objects.get().title == 'Hands off'


@pytest.mark.django_db
def test_process_is_chatty_when_verbose(webfeed, capsys):
    webfeed.verbose = 1

    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link></item>'
        ),
    )

    assert 'ID: g-1' in capsys.readouterr().out


@pytest.mark.django_db
def test_process_lets_a_subclass_hook_in(webfeed):
    seen = []

    def custom_process(entry, ent):
        seen.append(ent.id)
        entry.title = 'Rewritten'

    webfeed.custom_process = custom_process
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link></item>'
        ),
    )

    assert seen == ['g-1']
    assert Entry.objects.get().title == 'Rewritten'


@pytest.mark.django_db
def test_process_carries_media_content_into_the_mblob(webfeed):
    run_process(
        webfeed,
        build_feed(
            '<item><guid>g-1</guid><title>T</title><link>http://e/1</link>'
            '<media:content xmlns:media="http://search.yahoo.com/mrss/" '
            'url="http://e/clip.mp4" medium="video" /></item>'
        ),
    )

    assert 'http://e/clip.mp4' in Entry.objects.get().mblob


@pytest.mark.django_db
@pytest.mark.parametrize(
    'date_tag, rewritten',
    [
        # No update time: always rewritten, never compared to the publish date.
        ('<pubDate>Wed, 01 Nov 2023 12:00:00 GMT</pubDate>', True),
        ('<atom:updated>2023-11-01T12:00:00Z</atom:updated>', False),
    ],
)
def test_process_skips_only_entries_whose_update_time_has_not_moved(
    webfeed, date_tag, rewritten
):
    xml = build_feed(
        '<item><guid>g-1</guid><title>A Title</title>'
        '<link>http://example.com/1</link>%s</item>' % date_tag
    )
    run_process(webfeed, xml)
    Entry.objects.update(title='Edited locally')

    run_process(webfeed, xml)

    title = Entry.objects.get().title
    assert title == ('A Title' if rewritten else 'Edited locally')
