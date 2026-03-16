import pytest
from unittest.mock import patch
from glifestream.apis.selfposts import SelfpostsService


@pytest.mark.django_db
def test_selfposts_share_markdown(service):
    # Ensure service is selfposts
    service.api = 'selfposts'
    service.save()

    api = SelfpostsService(service)
    content = '# Hello\n\nThis is **bold**.'

    with patch('glifestream.utils.html.strip_script', side_effect=lambda x: x):
        entry = api.share({'content': content, 'title': 'Test Post'})

    assert entry is not None
    assert '<h1>Hello</h1>' in entry.content
    assert '<strong>bold</strong>' in entry.content


@pytest.mark.django_db
def test_selfposts_share_no_markdown_fallback(service):
    service.api = 'selfposts'
    service.save()

    with patch('glifestream.apis.selfposts.markdown', None):
        api = SelfpostsService(service)
        content = 'Line 1\nLine 2'
        entry = api.share({'content': content})
        # The content is escaped during processing in SelfpostsService
        assert 'Line 1&lt;br/&gt;Line 2' in entry.content
