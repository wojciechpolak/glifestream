from unittest.mock import patch, MagicMock
from glifestream.utils import oembed


@patch('glifestream.utils.httpclient.get')
def test_oembed_discover_flickr(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'title': 'Flickr Photo'}
    mock_get.return_value = mock_response

    result = oembed.discover('https://www.flickr.com/photos/123', 'flickr')
    assert result == {'title': 'Flickr Photo'}
    assert 'url=' in mock_get.call_args[0][0]


def test_oembed_discover_invalid_provider():
    assert oembed.discover('http://example.com', 'unknown') is None
