import pytest
import datetime
from urllib.parse import quote
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import override_settings
from glifestream.stream.models import Entry
from glifestream.testsupport.magic_sso import make_magic_sso_token

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


@pytest.fixture
def entries(db, service):
    # Create some entries for testing filters
    # Use UTC to bypass original code's timezone bugs
    e1 = Entry(
        service=service,
        title='Day 1',
        guid='g1',
        date_published=datetime.datetime(2023, 10, 1, 10, 0, tzinfo=UTC),
    )
    e1.save()
    e2 = Entry(
        service=service,
        title='Day 2',
        guid='g2',
        date_published=datetime.datetime(2023, 10, 2, 10, 0, tzinfo=UTC),
    )
    e2.save()
    # Different year
    e3 = Entry(
        service=service,
        title='Last Year',
        guid='g3',
        date_published=datetime.datetime(2022, 10, 1, 10, 0, tzinfo=UTC),
    )
    e3.save()


@pytest.mark.django_db
def test_index_date_year_filter(client, entries):
    url = '/2023/'  # Using hardcoded URL since original urls.py has no name
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['entries']) == 2


@pytest.mark.django_db
def test_index_date_month_filter(client, entries):
    url = '/2023/10/'  # Using hardcoded URL since original urls.py has no name
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['entries']) == 2
    assert response.context['page']['month_nav'] is True


@pytest.mark.django_db
def test_index_class_filter(client, entries, service):
    # Default cls for 'feed' api is 'feed'
    url = reverse('index') + '?class=feed'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['entries']) == 3

    # Non-existent class
    url = reverse('index') + '?class=non-existent'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['entries']) == 0


@pytest.mark.django_db
def test_index_ctx_filters(client, user, entries, service):
    # Public
    url = reverse('public')
    response = client.get(url)
    assert response.status_code == 200
    # Everything should be visible if services are public
    assert len(response.context['entries']) >= 3

    # Favorites (empty)
    admin_user = User.objects.create_superuser('admin2', 'admin@test.com', 'pass')
    client.force_login(admin_user)
    url = reverse('favorites')
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['entries']) == 0


@override_settings(ENTRIES_ON_PAGE=5)
@pytest.mark.django_db
def test_index_pagination(client, service):
    # Create 8 entries (page size 5)
    # Use UTC for consistency
    base_date = datetime.datetime(2023, 11, 1, 10, 0, tzinfo=UTC)
    for i in range(8):
        e = Entry(
            service=service,
            title=f'Entry {i}',
            guid=f'g{i}',
            link=f'http://{i}.com',
            date_published=base_date - datetime.timedelta(minutes=i),
        )
        e.save()

    url = reverse('index')
    response = client.get(url)
    assert len(response.context['entries']) == 5
    assert response.context['page']['start'] > 0

    next_start = response.context['page']['start']
    from unittest.mock import patch

    # Use a safe patching strategy to fix RuntimeWarning.
    # We patch fromtimestamp to return an AWARE UTC datetime.
    with patch('glifestream.stream.views.datetime') as mock_datetime_module:
        # Re-attach real functionality except for the parts we want to mock
        mock_datetime_module.date = datetime.date
        mock_datetime_module.timedelta = datetime.timedelta

        class MockDT:
            @classmethod
            def fromtimestamp(
                cls, ts: float, tz: datetime.tzinfo | None = None
            ) -> datetime.datetime:
                # Return aware UTC. Since system TZ is UTC, this is consistent.
                return datetime.datetime.fromtimestamp(ts, tz=UTC)

            @classmethod
            def utcnow(cls):
                return datetime.datetime.now(datetime.timezone.utc)

            @classmethod
            def now(cls, tz=None):
                return datetime.datetime.now(tz or UTC)

        mock_datetime_module.datetime = MockDT

        url = reverse('index') + f'?start={next_start}'
        response = client.get(url)

    # Page 2 should have results (Entry 5, 6, 7)
    assert len(response.context['entries']) > 0


@pytest.mark.django_db
def test_index_complex_filters(client, service):
    # Setup entries with different combinations
    Entry.objects.create(
        service=service,
        title='Python Test',
        guid='c1',
        author_name='Alice',
        date_published=datetime.datetime(2023, 11, 1, 10, 0, tzinfo=UTC),
    )
    Entry.objects.create(
        service=service,
        title='Django Test',
        guid='c2',
        author_name='Alice',
        date_published=datetime.datetime(2023, 11, 1, 11, 0, tzinfo=UTC),
    )
    Entry.objects.create(
        service=service,
        title='Random',
        guid='c3',
        author_name='Bob',
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )

    # Filter by author + class
    url = reverse('index') + '?author=Alice&class=feed'
    response = client.get(url)
    assert len(response.context['entries']) == 2


@pytest.mark.django_db
def test_index_invalid_params(client, service):
    Entry.objects.create(
        service=service,
        title='Test',
        guid='i1',
        date_published=datetime.datetime(2023, 11, 1, 10, 0, tzinfo=UTC),
    )

    # Invalid start (not a float/int) returns 404
    url = reverse('index') + '?start=invalid'
    response = client.get(url)
    assert response.status_code == 404

    # Invalid page p (not an int)
    url = reverse('index') + '?p=notint'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['entries']) == 1


@pytest.mark.django_db
def test_index_no_results(client, service):
    # s is for search, which might require sphinx.
    # But if SEARCH_ENGINE is internal, it might use basic query.
    url = reverse('index') + '?author=nonexistent'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['entries']) == 0


@override_settings(MAGICSSO_ENABLED=False)
@pytest.mark.django_db
def test_index_masks_friends_only_entries_for_anonymous_viewers(client, service):
    entry = Entry.objects.create(
        service=service,
        title='Friends Post',
        guid='fo-anon',
        content='Only friends should read this',
        friends_only=True,
        date_published=datetime.datetime(2023, 11, 1, 10, 0, tzinfo=UTC),
    )

    response = client.get(reverse('entry', args=[entry.pk]), follow=True)

    assert response.status_code == 200
    assert (
        b'The content of this entry is available only to my friends.'
        in response.content
    )
    assert b'Friends Login' not in response.content
    assert b'Only friends should read this' not in response.content


@override_settings(MAGICSSO_ENABLED=True)
@pytest.mark.django_db
def test_index_masks_friends_only_entries_with_magic_sso_login_when_enabled(
    client, service
):
    entry = Entry.objects.create(
        service=service,
        title='Friends Post',
        guid='fo-anon-sso',
        content='Only friends should read this',
        friends_only=True,
        date_published=datetime.datetime(2023, 11, 1, 10, 0, tzinfo=UTC),
    )

    response = client.get(reverse('entry', args=[entry.pk]), follow=True)

    assert response.status_code == 200
    assert b'Friends Login' in response.content
    expected_return_url = quote(f'http://testserver/entry/{entry.pk}/', safe='')
    assert (
        f'/friends/login/?returnUrl={expected_return_url}'.encode() in response.content
    )


@override_settings(MAGICSSO_ENABLED=True)
@pytest.mark.django_db
def test_index_reveals_friends_only_entries_for_magic_sso_friend(client, service):
    entry = Entry.objects.create(
        service=service,
        title='Friends Post',
        guid='fo-friend',
        content='Only friends should read this',
        friends_only=True,
        date_published=datetime.datetime(2023, 11, 1, 10, 0, tzinfo=UTC),
    )
    client.cookies[settings.MAGICSSO_COOKIE_NAME] = make_magic_sso_token()

    response = client.get(reverse('entry', args=[entry.pk]), follow=True)

    assert response.status_code == 200
    assert b'Only friends should read this' in response.content
    assert (
        b'The content of this entry is available only to my friends.'
        not in response.content
    )
    assert response.context['friend'] is True
    assert response.context['friend_email'] == 'friend@example.com'


@pytest.mark.django_db
def test_index_shows_separate_login_links_for_anonymous(client):
    response = client.get(reverse('index'))

    assert response.status_code == 200
    assert b'>Login<' in response.content
    assert b'Friends Login' not in response.content
    assert b'Admin Login' not in response.content


@override_settings(MAGICSSO_ENABLED=False)
@pytest.mark.django_db
def test_index_shows_friend_header_for_magic_sso_viewer(client):
    client.cookies[settings.MAGICSSO_COOKIE_NAME] = make_magic_sso_token(
        email='reader@example.com'
    )

    response = client.get(reverse('index'))

    assert response.status_code == 200
    assert b'reader@example.com' not in response.content
    assert b'>Login<' in response.content


@override_settings(MAGICSSO_ENABLED=True)
@pytest.mark.django_db
def test_index_shows_friend_header_for_magic_sso_viewer_when_enabled(client):
    client.cookies[settings.MAGICSSO_COOKIE_NAME] = make_magic_sso_token(
        email='reader@example.com'
    )

    response = client.get(reverse('index'))

    assert response.status_code == 200
    assert b'reader@example.com' in response.content
    assert b'>Login<' not in response.content
