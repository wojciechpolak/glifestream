import pytest
import datetime
from unittest.mock import patch, MagicMock
from glifestream.apis.webfeed import WebfeedService
from glifestream.stream.models import Entry

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
                mock_response.text = 'empty'
                mock_response.headers = {'etag': 'etag-123'}
                mock_http.get.return_value = mock_response
                mock_http.gen_auth.return_value = {}
                mock_http.get_alturl_if_html.return_value = None

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
        api.run()

        # Should not process if bozo is True (and not encoding override)
        assert Entry.objects.count() == 0


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
