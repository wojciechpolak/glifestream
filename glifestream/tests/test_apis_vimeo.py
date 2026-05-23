import pytest
from unittest.mock import patch

from glifestream.apis.vimeo import VimeoService
from glifestream.utils import httpclient


@pytest.mark.django_db
def test_vimeo_fetch_error_propagates(service):
    service.api = 'vimeo'
    service.url = 'channel/staffpicks'
    service.save()

    api = VimeoService(service)

    with patch(
        'glifestream.apis.vimeo.httpclient.get',
        side_effect=httpclient.build_fetch_error(
            category='remote_5xx',
            detail='HTTP 503 Service Unavailable from https://vimeo.com/api/v2/channel/staffpicks/videos.json',
            retryable=True,
            status_code=503,
            url='https://vimeo.com/api/v2/channel/staffpicks/videos.json',
        ),
    ), pytest.raises(httpclient.FetchError) as excinfo:
            api.run()

    assert excinfo.value.category == 'remote_5xx'
