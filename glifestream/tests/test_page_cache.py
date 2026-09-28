import datetime
import json
import re

import pytest
from django.core.cache import cache
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from glifestream.gauth.models import UserProfile
from glifestream.stream.models import Entry, Service
from glifestream.utils import page_cache

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def page_cache_on(settings):
    settings.CACHES = {
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}
    }
    settings.CACHE_MIDDLEWARE_SECONDS = 600
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def service():
    return Service.objects.create(
        api='webfeed', name='Feed', url='https://example.org/feed', public=True
    )


@pytest.fixture
def entry(service):
    now = timezone.now()
    return Entry.objects.create(
        service=service,
        guid='e-1',
        title='First title',
        link='https://example.org/1',
        date_published=now,
        date_updated=now,
    )


# The HTML pages renew the CSRF cookie in every answer, so Django caches
# none of them; the feeds are cached.
def feed_url() -> str:
    return reverse('public') + '?format=atom'


def page(client) -> str:
    return str(client.get(feed_url()).content.decode())


def change_title_unseen(entry: Entry, title: str) -> None:
    """Changes the row behind Django's back, to see whether a page is cached."""
    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE stream_entry SET title = %s WHERE id = %s', [title, entry.pk]
        )


def test_a_page_is_served_from_the_cache(client, entry):
    assert 'First title' in page(client)

    change_title_unseen(entry, 'Unseen title')

    assert 'First title' in page(client)


def test_saving_an_entry_empties_the_cache(client, entry):
    assert 'First title' in page(client)

    entry.title = 'Saved title'
    entry.save()

    assert 'Saved title' in page(client)


def test_hiding_an_entry_with_an_update_empties_the_cache(client, entry):
    assert 'First title' in page(client)

    Entry.objects.filter(pk=entry.pk).update(active=False)

    assert 'First title' not in page(client)


def test_deleting_an_entry_empties_the_cache(client, entry):
    assert 'First title' in page(client)

    entry.delete()

    assert 'First title' not in page(client)


def test_a_service_made_private_leaves_the_public_stream(client, service, entry):
    assert 'First title' in page(client)

    service.public = False
    service.save()

    assert 'First title' not in page(client)


def test_a_fetch_saving_its_service_keeps_the_cache(client, service, entry):
    assert 'First title' in page(client)
    change_title_unseen(entry, 'Unseen title')

    service.last_checked = timezone.now()
    service.etag = 'abc'
    service.save()
    Service.objects.get(pk=service.pk).save(update_fields=['next_fetch_at'])

    assert 'First title' in page(client)


def test_a_preference_empties_the_cache(client, entry, django_user_model):
    assert 'First title' in page(client)
    change_title_unseen(entry, 'Unseen title')

    user = django_user_model.objects.create_user(username='u', password='p')
    UserProfile.objects.create(user=user, fold_lines=8)

    assert 'Unseen title' in page(client)


def test_the_browser_keeps_no_copy(client, entry):
    for response in (client.get(feed_url()), client.get(feed_url())):
        assert 'max-age=0' in response['Cache-Control']
        assert not response.has_header('Expires')


def test_a_lost_generation_does_not_bring_back_older_pages(client, entry):
    first = page_cache.generation()
    cache.delete(page_cache.GENERATION_KEY)

    assert page_cache.generation() != first


def archive_months(client) -> list[str]:
    html = client.get(reverse('index')).content.decode()
    data = re.search(r'id="gls-stream-data"[^>]*>(.*?)</script>', html, re.S)
    assert data
    months: list[str] = json.loads(data.group(1))['archives']
    return months


def add_entry(service: Service, guid: str, year: int, month: int) -> Entry:
    date = datetime.datetime(year, month, 15, tzinfo=datetime.UTC)
    return Entry.objects.create(
        service=service,
        guid=guid,
        title=guid,
        link='https://example.org/' + guid,
        date_published=date,
        date_updated=date,
    )


def move_unseen(entry: Entry, year: int, month: int) -> None:
    """Moves the entry behind Django's back, to see whether months are kept."""
    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE stream_entry SET date_published = %s WHERE id = %s',
            [datetime.datetime(year, month, 15), entry.pk],
        )


def test_the_archive_months_are_kept_until_an_entry_changes(client, service):
    old = add_entry(service, 'old', 2020, 1)
    assert archive_months(client) == ['2020/01']

    move_unseen(old, 2019, 5)
    assert archive_months(client) == ['2020/01']

    add_entry(service, 'new', 2021, 3)
    assert archive_months(client) == ['2021/03', '2019/05']


def test_each_view_keeps_its_own_archive_months(client, admin_client, service):
    add_entry(service, 'public', 2020, 1)
    private = Service.objects.create(
        api='webfeed', name='Private', url='https://example.org/private'
    )
    add_entry(private, 'private', 2019, 5)

    assert archive_months(admin_client) == ['2020/01', '2019/05']
    assert archive_months(client) == ['2020/01']


def test_a_cache_that_keeps_nothing_computes_every_time(settings):
    settings.CACHES = {
        'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}
    }
    calls = []

    def compute() -> int:
        calls.append(1)
        return len(calls)

    assert page_cache.remember('n', 'k', compute) == 1
    assert page_cache.remember('n', 'k', compute) == 2


def test_a_remembered_empty_value_is_not_computed_again():
    calls = []

    def compute() -> list[int]:
        calls.append(1)
        return []

    page_cache.remember('n', 'k', compute)
    page_cache.remember('n', 'k', compute)

    assert calls == [1]
