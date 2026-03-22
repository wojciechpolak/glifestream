import datetime
import pytest
from unittest.mock import patch
from django.conf import settings
from glifestream.stream.models import Entry
from glifestream.apis.selfposts import SelfpostsService

UTC = datetime.timezone.utc


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
        assert entry is not None
        assert 'Line 1&lt;br/&gt;Line 2' in entry.content


@pytest.mark.django_db
def test_selfposts_share_parses_string_boolean_flags(service):
    service.api = 'selfposts'
    service.save()

    api = SelfpostsService(service)
    with patch(
        'glifestream.apis.selfposts.utcnow',
        side_effect=[
            datetime.datetime(2026, 3, 22, 17, 0, 0, tzinfo=UTC),
            datetime.datetime(2026, 3, 22, 17, 0, 1, tzinfo=UTC),
        ],
    ):
        private_entry = api.share(
            {'content': 'Private draft', 'draft': '1', 'friends_only': '1'}
        )
        public_entry = api.share(
            {'content': 'Public post', 'draft': '0', 'friends_only': '0'}
        )

    assert private_entry is not None
    assert private_entry.draft is True
    assert private_entry.friends_only is True

    assert public_entry is not None
    assert public_entry.draft is False
    assert public_entry.friends_only is False


@pytest.mark.django_db
def test_selfposts_reshare_parses_string_as_me_flag(service, user):
    service.api = 'selfposts'
    service.save()
    user.first_name = 'Test'
    user.last_name = 'User'
    user.save()

    source = Entry.objects.create(
        service=service,
        title='Original',
        guid='reshare-source',
        link='http://example.com/original',
        content='Original content',
        author_name='Original Author',
    )
    api = SelfpostsService(service)

    with (
        patch(
            'glifestream.apis.selfposts.utcnow',
            side_effect=[
                datetime.datetime(2026, 3, 22, 17, 1, 0, tzinfo=UTC),
                datetime.datetime(2026, 3, 22, 17, 1, 1, tzinfo=UTC),
            ],
        ),
        patch('glifestream.stream.media.transform_to_local'),
        patch('glifestream.stream.media.extract_and_register'),
    ):
        same_author = api.reshare(source, {'as_me': '0', 'user': user})
        as_me_entry = api.reshare(source, {'as_me': '1', 'user': user})

    assert same_author is not None
    assert same_author.author_name == 'Original Author'
    assert same_author.link == source.link

    assert as_me_entry is not None
    assert as_me_entry.author_name == 'Test User'
    assert as_me_entry.link == settings.BASE_URL + '/'
