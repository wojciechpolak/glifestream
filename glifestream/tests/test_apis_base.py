import datetime

import pytest

from glifestream.apis.base import BaseService, post_title, set_reblog
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


@pytest.mark.django_db
def test_resolve_entry_builds_an_unsaved_entry_for_a_new_guid(service):
    e = _Service(service).resolve_entry('new-guid', NOON)

    assert e is not None
    assert e.pk is None
    assert (e.service, e.guid) == (service, 'new-guid')


def test_resolve_entry_returns_the_stored_entry_when_newer(service, stored):
    assert _Service(service).resolve_entry('guid-1', NOON + HOUR) == stored


@pytest.mark.parametrize('updated', [NOON, NOON - HOUR])
def test_resolve_entry_skips_an_entry_that_has_not_changed(service, stored, updated):
    assert _Service(service).resolve_entry('guid-1', updated) is None


def test_resolve_entry_force_overwrite_ignores_freshness(service, stored):
    api = _Service(service, force_overwrite=True)
    assert api.resolve_entry('guid-1', NOON - HOUR) == stored


def test_resolve_entry_without_a_timestamp_skips_the_freshness_check(service, stored):
    assert _Service(service).resolve_entry('guid-1', None) == stored


def test_resolve_entry_never_rewrites_a_protected_entry(service, stored):
    stored.protected = True
    stored.save()

    api = _Service(service, force_overwrite=True)
    assert api.resolve_entry('guid-1', NOON + HOUR) is None


def test_post_title_strips_markup_and_mention_sigils():
    html = '<p>Hello @alice and #friends, this is a long post body</p>'
    assert post_title(html) == 'Hello alice and friends, this is a...'


def test_set_reblog_marks_and_clears_a_reshare():
    e = Entry()
    set_reblog(e, True, 'Bob', 'https://example.com/r/1')
    assert (e.reblog, e.reblog_by, e.reblog_uri) == (
        True,
        'Bob',
        'https://example.com/r/1',
    )

    set_reblog(e, False, 'ignored', 'ignored')
    assert (e.reblog, e.reblog_by, e.reblog_uri) == (False, '', '')
