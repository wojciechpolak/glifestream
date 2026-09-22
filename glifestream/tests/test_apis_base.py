import datetime

import pytest

from glifestream.apis.base import BaseService, post_title, set_reblog
from glifestream.ingestion import Candidate, NormalizedEntry
from glifestream.stream.models import Entry


class _Service(BaseService):
    name = 'Test'
    limit_sec = 0

    def run(self) -> None:
        pass


NOON = datetime.datetime(2024, 5, 1, 12, 0, tzinfo=datetime.timezone.utc)
HOUR = datetime.timedelta(hours=1)


@pytest.fixture
def stored(service):
    return Entry.objects.create(
        service=service,
        guid='guid-1',
        title='Stored',
        date_published=NOON,
        date_updated=NOON,
    )


def test_resolve_entry_is_deprecated_but_keeps_its_rules(service, stored):
    api = _Service(service, force_overwrite=True)
    with pytest.deprecated_call():
        assert api.resolve_entry('guid-1', NOON - HOUR) == stored
    with pytest.deprecated_call():
        new = api.resolve_entry('new-guid', NOON)
    assert new is not None and new.pk is None


def _candidate(guid, freshness, title):
    return Candidate(guid, freshness, lambda: NormalizedEntry(guid, title=title))


def test_ingest_sums_every_call_into_last_result(service, stored):
    api = _Service(service)
    api.ingest([_candidate('guid-1', NOON + HOUR, 'Changed')])
    api.ingest([_candidate('guid-2', NOON, 'New'), _candidate('guid-1', NOON, 'x')])

    assert (
        api.last_result.created,
        api.last_result.updated,
        api.last_result.skipped,
    ) == (1, 1, 1)


def test_ingest_honours_force_overwrite(service, stored):
    api = _Service(service, force_overwrite=True)
    api.ingest([_candidate('guid-1', NOON - HOUR, 'Forced')])

    stored.refresh_from_db()
    assert stored.title == 'Forced'


def test_post_title_strips_markup_and_mention_sigils():
    html = '<p>Hello @alice and #friends, this is a long post body</p>'
    assert post_title(html) == 'Hello alice and friends, this is a...'


@pytest.mark.parametrize('target', [Entry, lambda: NormalizedEntry('g')])
def test_set_reblog_marks_and_clears_a_reshare(target):
    e = target()
    set_reblog(e, True, 'Bob', 'https://example.com/r/1')
    assert (e.reblog, e.reblog_by, e.reblog_uri) == (
        True,
        'Bob',
        'https://example.com/r/1',
    )

    set_reblog(e, False, 'ignored', 'ignored')
    assert (e.reblog, e.reblog_by, e.reblog_uri) == (False, '', '')
