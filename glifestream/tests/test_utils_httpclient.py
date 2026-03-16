from unittest.mock import patch, MagicMock
from glifestream.utils import httpclient
from requests import Response


@patch('requests.get')
def test_get_request(mock_get):
    mock_get.return_value.status_code = 200
    response = httpclient.get('example.com')
    assert response.status_code == 200
    mock_get.assert_called_once()
    # Check if http:// was prepended
    assert mock_get.call_args[0][0] == 'http://example.com'


@patch('requests.post')
def test_post_request(mock_post):
    mock_post.return_value.status_code = 201
    response = httpclient.post('example.com', data={'key': 'value'})
    assert response.status_code == 201
    mock_post.assert_called_once()


def test_get_alturl_if_html():
    mock_response = MagicMock(spec=Response)
    mock_response.headers = {'content-type': 'text/html; charset=UTF-8'}
    mock_response.text = '<html><head><link rel="alternate" type="application/rss+xml" href="/rss.xml"></head></html>'
    mock_response.url = 'http://example.com/'

    alt_url = httpclient.get_alturl_if_html(mock_response)
    assert alt_url == 'http://example.com/rss.xml'


def test_gen_auth():
    from glifestream.stream.models import Service

    service = Service(creds='user:pass')
    assert httpclient.gen_auth(service) == ['user', 'pass']

    service_none = Service(creds='')
    assert httpclient.gen_auth(service_none) is None
