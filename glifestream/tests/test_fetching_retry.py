from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from glifestream.fetching import (
    FetchFailure,
    claim_runnable_jobs,
    classify_fetch_failure,
    compute_retry_at,
    describe_failure_backoff,
    enqueue_manual_fetch,
    run_service_fetch,
    serialize_fetch_state,
)
from glifestream.stream.models import ServiceFetchState
from glifestream.utils import httpclient

RETRYABLE = ServiceFetchState.FAILURE_RETRYABLE
TERMINAL = ServiceFetchState.FAILURE_TERMINAL


@pytest.fixture
def feed(service, settings):
    settings.FETCH_RETRY_BASE_SEC = 60
    settings.FETCH_TERMINAL_DELAY_SEC = 24 * 3600
    service.api = 'webfeed'
    service.fetch_interval_sec = 600
    service.save()
    return service


def timeout_error(**kwargs):
    return httpclient.build_fetch_error(
        category='timeout', detail='timed out', retryable=True, **kwargs
    )


def not_found_error():
    return httpclient.build_fetch_error(
        category='remote_4xx', detail='HTTP 404', retryable=False, status_code=404
    )


def retry_delay(service, failure, attempt) -> timedelta:
    now = timezone.now()
    retry_at = compute_retry_at(service, failure, attempt, now=now)
    assert retry_at is not None
    delay: timedelta = retry_at - now
    return delay


def delay_of(service, failure, attempt) -> int:
    return retry_delay(service, failure, attempt).seconds


# --- classification -------------------------------------------------------------


def test_a_retryable_fetch_error_keeps_its_category_and_retry_after():
    failure = classify_fetch_failure(timeout_error(retry_after_sec=90))
    assert failure == FetchFailure(RETRYABLE, 'timeout', 90)


def test_a_non_retryable_fetch_error_is_terminal():
    assert classify_fetch_failure(not_found_error()) == FetchFailure(
        TERMINAL, 'remote_4xx'
    )


def test_any_other_exception_is_retryable():
    assert classify_fetch_failure(KeyError('title')) == FetchFailure(
        RETRYABLE, 'unexpected'
    )


# --- retry schedule -------------------------------------------------------------


@pytest.mark.django_db
def test_retryable_failures_back_off_up_to_the_interval(feed):
    failure = FetchFailure(RETRYABLE, 'timeout')

    delays = [delay_of(feed, failure, attempt) for attempt in range(1, 8)]

    assert delays == [60, 120, 240, 480, 600, 600, 600]


@pytest.mark.django_db
def test_a_long_failure_streak_does_not_overflow(feed):
    assert delay_of(feed, FetchFailure(RETRYABLE, 'timeout'), 10_000) == 600


@pytest.mark.django_db
def test_a_longer_retry_after_wins_and_a_shorter_one_does_not(feed):
    assert delay_of(feed, FetchFailure(RETRYABLE, 'rate_limited', 900), 1) == 900
    assert delay_of(feed, FetchFailure(RETRYABLE, 'rate_limited', 5), 3) == 240


@pytest.mark.django_db
def test_a_terminal_failure_waits_the_terminal_delay(feed):
    delay = retry_delay(feed, FetchFailure(TERMINAL, 'remote_4xx'), 1)

    assert delay == timedelta(hours=24)


@pytest.mark.django_db
def test_a_terminal_failure_keeps_a_longer_interval(feed, settings):
    settings.FETCH_TERMINAL_DELAY_SEC = 300

    assert delay_of(feed, FetchFailure(TERMINAL, 'auth'), 1) == 600


@pytest.mark.django_db
def test_an_inactive_service_is_not_rescheduled(feed):
    feed.active = False

    assert compute_retry_at(feed, FetchFailure(RETRYABLE, 'x'), 1, now=0) is None


@pytest.mark.django_db
def test_a_service_without_an_interval_is_not_rescheduled(feed):
    with patch('glifestream.fetching.get_effective_interval_sec', return_value=None):
        assert compute_retry_at(feed, FetchFailure(RETRYABLE, 'x'), 1, now=0) is None


# --- recorded state -------------------------------------------------------------


def running_state(service):
    return ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_RUNNING,
        worker_token='token',
    )


def fetch(service, state, *, error=None):
    run = Mock(side_effect=error) if error else Mock()
    ServiceFetchState.objects.filter(pk=state.pk).update(
        status=ServiceFetchState.STATUS_RUNNING, worker_token='token'
    )
    with patch(
        'glifestream.fetching.ServiceFactory.create_service',
        return_value=Mock(run=run),
    ):
        if error:
            with pytest.raises(type(error)):
                run_service_fetch(service, state_id=state.pk, worker_token='token')
        else:
            run_service_fetch(service, state_id=state.pk, worker_token='token')
    state.refresh_from_db()
    service.refresh_from_db()


@pytest.mark.django_db
def test_each_failure_counts_and_pushes_the_next_fetch_further(feed):
    state = running_state(feed)
    delays = []

    for _ in range(3):
        fetch(feed, state, error=timeout_error())
        delays.append((feed.next_fetch_at - state.finished_at).seconds)

    assert delays == [60, 120, 240]
    assert state.consecutive_failures == 3
    assert (state.failure_kind, state.failure_category) == (RETRYABLE, 'timeout')


@pytest.mark.django_db
def test_a_terminal_failure_is_recorded_as_such(feed):
    state = running_state(feed)

    fetch(feed, state, error=not_found_error())

    assert (state.failure_kind, state.failure_category) == (TERMINAL, 'remote_4xx')
    assert feed.next_fetch_at - state.finished_at == timedelta(hours=24)


@pytest.mark.django_db
def test_a_success_resets_the_failure_streak(feed):
    state = running_state(feed)
    fetch(feed, state, error=timeout_error())
    fetch(feed, state, error=timeout_error())

    fetch(feed, state)

    assert state.status == ServiceFetchState.STATUS_SUCCEEDED
    assert (state.consecutive_failures, state.failure_kind) == (0, '')
    assert state.failure_category == ''
    assert feed.next_fetch_at - state.finished_at == timedelta(seconds=600)


@pytest.mark.django_db
def test_a_failed_manual_fetch_continues_the_streak(feed):
    state = running_state(feed)
    fetch(feed, state, error=timeout_error())
    ServiceFetchState.objects.filter(pk=state.pk).update(
        status=ServiceFetchState.STATUS_FAILED, worker_token=''
    )

    enqueue_manual_fetch(feed, wake_worker=False)
    [(state_id, _)] = claim_runnable_jobs('manual-token')
    with (
        patch(
            'glifestream.fetching.ServiceFactory.create_service',
            return_value=Mock(run=Mock(side_effect=timeout_error())),
        ),
        pytest.raises(httpclient.FetchError),
    ):
        run_service_fetch(feed, state_id=state_id, worker_token='manual-token')

    state.refresh_from_db()
    assert state.consecutive_failures == 2


@pytest.mark.django_db
def test_a_stale_worker_token_leaves_the_state_alone(feed):
    state = running_state(feed)

    with (
        patch(
            'glifestream.fetching.ServiceFactory.create_service',
            return_value=Mock(run=Mock(side_effect=timeout_error())),
        ),
        pytest.raises(httpclient.FetchError),
    ):
        run_service_fetch(feed, state_id=state.pk, worker_token='someone-else')

    state.refresh_from_db()
    assert (state.status, state.consecutive_failures) == (
        ServiceFetchState.STATUS_RUNNING,
        0,
    )


@pytest.mark.django_db
def test_a_fetch_without_a_state_backs_off_once(feed):
    with (
        patch(
            'glifestream.fetching.ServiceFactory.create_service',
            return_value=Mock(run=Mock(side_effect=timeout_error())),
        ),
        pytest.raises(httpclient.FetchError),
    ):
        run_service_fetch(feed)

    feed.refresh_from_db()
    assert timezone.now() < feed.next_fetch_at <= timezone.now() + timedelta(seconds=60)


# --- status tab -----------------------------------------------------------------


@pytest.mark.django_db
def test_the_status_payload_describes_the_failure_streak(feed):
    state = running_state(feed)
    fetch(feed, state, error=timeout_error())
    fetch(feed, state, error=timeout_error())

    payload = serialize_fetch_state(feed)

    assert payload['consecutive_failures'] == 2
    assert payload['failure_kind'] == RETRYABLE
    assert payload['failure_category'] == 'timeout'
    assert payload['failure_note'] == (
        'Failed 2 times in a row. Retrying sooner than usual.'
    )


@pytest.mark.parametrize(
    'count, kind, note',
    [
        (0, '', ''),
        (1, RETRYABLE, 'Failed 1 time in a row. Retrying sooner than usual.'),
        (
            1,
            TERMINAL,
            'Failed 1 time in a row. The error does not look temporary, '
            'so fetches are slowed down.',
        ),
        (
            4,
            TERMINAL,
            'Failed 4 times in a row. The error does not look temporary, '
            'so fetches are slowed down.',
        ),
    ],
)
def test_failure_notes(count, kind, note):
    state = ServiceFetchState(consecutive_failures=count, failure_kind=kind)

    assert describe_failure_backoff(state) == note
    assert describe_failure_backoff(None) == ''


@pytest.mark.django_db
def test_the_status_payload_without_a_state(feed):
    payload = serialize_fetch_state(feed)

    assert (payload['consecutive_failures'], payload['failure_note']) == (0, '')
    assert (payload['failure_kind'], payload['failure_category']) == ('', '')
