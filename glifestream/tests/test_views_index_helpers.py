import datetime
from unittest.mock import patch
from typing import Any, cast

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory, override_settings

from glifestream.stream.index_view import (
    apply_archive_filters,
    apply_context_filters,
    apply_query_string_filters,
    apply_start_pagination,
    build_index_query_state,
    build_index_request_state,
    decorate_entries,
    dispatch_index_format,
    run_index_query,
    validate_exact_entry_request,
)
from glifestream.stream.models import Entry, List

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
def request_factory():
    return RequestFactory()


def _build_state(request, args):
    return build_index_request_state(request, args)


@pytest.mark.django_db
def test_apply_archive_filters_builds_month_navigation(request_factory):
    request = request_factory.get('/2023/10/')
    request.user = AnonymousUser()

    state = _build_state(request, {'year': 2023, 'month': 10})
    query = build_index_query_state(state)
    apply_archive_filters(query)

    assert query.filters['date_published__year'] == 2023
    assert query.filters['date_published__month'] == 10
    assert query.page['backtime'] is False
    assert query.page['month_nav'] is True
    assert query.page['month_prev'] == '2023/09'
    assert query.page['month_next'] == '2023/11'
    assert query.page['title'] == '2023/10'


@pytest.mark.django_db
def test_apply_context_filters_redirects_anonymous_favorites(request_factory):
    request = request_factory.get('/favorites/')
    request.user = AnonymousUser()

    state = _build_state(request, {'ctx': 'favorites'})
    query = build_index_query_state(state)
    apply_archive_filters(query)

    response = apply_context_filters(state, query)

    assert response is not None
    assert response.status_code == 302
    assert response['Location'].endswith('/')


@pytest.mark.django_db
def test_apply_context_filters_sets_list_scope(request_factory, user, service):
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    stream_list = List.objects.create(user=user, name='Reading Queue')
    stream_list.services.add(service)

    request = request_factory.get(f'/list/{stream_list.slug}/')
    request.user = user

    state = _build_state(request, {'list': stream_list.slug})
    query = build_index_query_state(state)
    apply_archive_filters(query)

    response = apply_context_filters(state, query)

    assert response is None
    assert 'service__home' not in query.filters
    assert list(query.filters['service__id__in']) == [{'id': service.id}]
    assert query.page['ctx'] == f'list/{stream_list.slug}'
    assert query.page['title'] == stream_list.slug


@pytest.mark.django_db
def test_apply_query_string_filters_builds_filters_and_urlparams(
    request_factory, user
):
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    request = request_factory.get(
        '/?class=feed&author=Alice&service=feed&reblogs=0'
    )
    request.user = user

    state = _build_state(request, {})
    query = build_index_query_state(state)
    apply_archive_filters(query)
    apply_context_filters(state, query)
    apply_query_string_filters(state, query)

    assert query.filters['service__cls'] == 'feed'
    assert query.filters['author_name'] == 'Alice'
    assert query.filters['service__api'] == 'feed'
    assert query.filters['reblog'] is False
    assert query.page['reblogs'] is False
    assert query.urlparams == ['class=feed', 'author=Alice', 'service=feed']


@override_settings(ENTRIES_ON_PAGE=2)
@pytest.mark.django_db
def test_apply_start_pagination_computes_after_for_reverse_and_archive_orders(
    request_factory, service
):
    entries = []
    base_date = datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC)
    for idx in range(4):
        entries.append(
            Entry.objects.create(
                service=service,
                title=f'Entry {idx}',
                guid=f'start-{idx}',
                date_published=base_date - datetime.timedelta(hours=idx),
            )
        )

    request = request_factory.get(
        '/?start=%s' % int(entries[2].date_published.timestamp())
    )
    request.user = AnonymousUser()
    reverse_state = _build_state(request, {})
    reverse_query = build_index_query_state(reverse_state)
    apply_archive_filters(reverse_query)
    apply_context_filters(reverse_state, reverse_query)

    with patch('glifestream.stream.index_view.datetime') as mock_datetime_module:
        mock_datetime_module.date = datetime.date
        mock_datetime_module.timedelta = datetime.timedelta
        mock_datetime_module.timezone = datetime.timezone

        class MockDT:
            @classmethod
            def fromtimestamp(
                cls, ts: float, tz: datetime.tzinfo | None = None
            ) -> datetime.datetime:
                return datetime.datetime.fromtimestamp(ts, tz=UTC)

            @classmethod
            def now(cls, tz=None):
                return datetime.datetime.now(tz or UTC)

        mock_datetime_module.datetime = MockDT
        reverse_after = apply_start_pagination(reverse_state, reverse_query)

    assert reverse_after == int(entries[0].date_published.timestamp())

    archive_request = request_factory.get(
        '/2023/?start=%s' % int(entries[1].date_published.timestamp())
    )
    archive_request.user = AnonymousUser()
    archive_state = _build_state(archive_request, {'year': 2023})
    archive_query = build_index_query_state(archive_state)
    apply_archive_filters(archive_query)
    apply_context_filters(archive_state, archive_query)

    with patch('glifestream.stream.index_view.datetime') as mock_datetime_module:
        mock_datetime_module.date = datetime.date
        mock_datetime_module.timedelta = datetime.timedelta
        mock_datetime_module.timezone = datetime.timezone
        mock_datetime_module.datetime = MockDT
        archive_after = apply_start_pagination(archive_state, archive_query)

    assert archive_after == int(entries[3].date_published.timestamp())


@pytest.mark.django_db
def test_apply_start_pagination_rejects_invalid_timestamp(request_factory):
    request = request_factory.get('/?start=invalid')
    request.user = AnonymousUser()

    state = _build_state(request, {})
    query = build_index_query_state(state)
    apply_archive_filters(query)
    apply_context_filters(state, query)

    with pytest.raises(Http404):
        apply_start_pagination(state, query)


@override_settings(SEARCH_ENABLE=True, SEARCH_ENGINE='db', ENTRIES_ON_PAGE=2)
@pytest.mark.django_db
def test_run_index_query_search_sets_prev_next_and_filters_friends_only(
    request_factory, service
):
    service.public = True
    service.save(update_fields=['public'])
    for idx in range(5):
        Entry.objects.create(
            service=service,
            title=f'Visible {idx}',
            guid=f'search-{idx}',
            content='python term',
            date_published=datetime.datetime(2023, 11, 1, 12, idx, tzinfo=UTC),
        )
    Entry.objects.create(
        service=service,
        title='Friends Only',
        guid='search-friends',
        content='python term',
        friends_only=True,
        date_published=datetime.datetime(2023, 11, 1, 13, 0, tzinfo=UTC),
    )

    request = request_factory.get('/?s=python%20term&page=2')
    request.user = AnonymousUser()

    state = _build_state(request, {})
    query = build_index_query_state(state)
    apply_archive_filters(query)
    apply_context_filters(state, query)
    apply_query_string_filters(state, query)

    result = run_index_query(state, query)
    titles = [entry.title for entry in result.entries]

    assert len(result.entries) == 2
    assert result.extra_page['prevpage'] == 1
    assert result.extra_page['nextpage'] == 3
    assert 'Friends Only' not in titles


@override_settings(MAGICSSO_ENABLED=True)
@pytest.mark.django_db
def test_decorate_entries_builds_slugged_and_friends_only_links(
    request_factory, service
):
    public_entry = Entry.objects.create(
        service=service,
        title='Hello World Entry',
        guid='decorate-public',
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    friends_entry = Entry.objects.create(
        service=service,
        title='Friends Entry',
        guid='decorate-friends',
        friends_only=True,
        date_published=datetime.datetime(2023, 11, 1, 11, 0, tzinfo=UTC),
    )

    request = request_factory.get('/')
    request.user = AnonymousUser()
    state = _build_state(request, {})
    query = build_index_query_state(state)
    query.page['title'] = 'Exact'

    decorate_entries(state, query, [public_entry, friends_entry])

    public_entry = cast(Any, public_entry)
    friends_entry = cast(Any, friends_entry)

    assert public_entry.gls_link.endswith('/hello-world-entry')
    assert public_entry.gls_absolute_link == f'http://testserver{public_entry.gls_link}'
    assert public_entry.friends_login_url.endswith(
        'returnUrl='
        f'http%3A%2F%2Ftestserver%2Fentry%2F{public_entry.pk}%2Fhello-world-entry'
    )
    assert friends_entry.gls_link == f'/entry/{friends_entry.pk}/'
    assert 'title' not in query.page


@pytest.mark.django_db
def test_validate_exact_entry_request_redirects_to_slugged_path(
    request_factory, service
):
    entry = Entry.objects.create(
        service=service,
        title='Needs Canonical Path',
        guid='canonical',
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )

    request = request_factory.get(f'/entry/{entry.pk}')
    request.user = AnonymousUser()
    state = _build_state(request, {'entry': entry.pk})
    query = build_index_query_state(state)
    query.page['exactentry'] = True

    decorate_entries(state, query, [entry])
    entry = cast(Any, entry)
    response = validate_exact_entry_request(state, query, [entry])

    assert response is not None
    assert response.status_code == 301
    assert response['Location'].endswith('/needs-canonical-path')


@pytest.mark.django_db
def test_dispatch_index_format_rejects_unknown_format(request_factory):
    request = request_factory.get('/?format=bogus')
    request.user = AnonymousUser()

    state = _build_state(request, {})
    query = build_index_query_state(state)
    apply_archive_filters(query)
    apply_context_filters(state, query)

    with pytest.raises(Http404):
        dispatch_index_format(state, query, run_index_query(state, query))
