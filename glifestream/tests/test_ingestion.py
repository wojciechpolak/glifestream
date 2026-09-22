import datetime
from unittest.mock import patch

import pytest

from glifestream.ingestion import (
    UNSET,
    Candidate,
    ImportResult,
    NormalizedEntry,
    ingest,
    resolve_entry,
)
from glifestream.stream.models import Entry, Media

NOON = datetime.datetime(2024, 5, 1, 12, 0, tzinfo=datetime.timezone.utc)
HOUR = datetime.timedelta(hours=1)
THUMB = '[GLS-THUMBS]/abcdef0123456789'


@pytest.fixture
def stored(service):
    return Entry.objects.create(
        service=service,
        guid='guid-1',
        title='Stored',
        author_name='Stored author',
        content='Stored content',
        date_published=NOON,
        date_updated=NOON,
    )


def candidate(guid='guid-1', freshness=NOON + HOUR, **fields):
    fields.setdefault('title', 'Imported')
    return Candidate(guid, freshness, lambda: NormalizedEntry(guid, **fields))


# --- resolve_entry ------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_entry_builds_an_unsaved_entry_for_a_new_guid(service):
    e = resolve_entry(service, 'new-guid', NOON)

    assert e is not None
    assert e.pk is None
    assert (e.service, e.guid) == (service, 'new-guid')


def test_resolve_entry_returns_the_stored_entry_when_newer(service, stored):
    assert resolve_entry(service, 'guid-1', NOON + HOUR) == stored


@pytest.mark.parametrize('updated', [NOON, NOON - HOUR])
def test_resolve_entry_skips_an_entry_that_has_not_changed(service, stored, updated):
    assert resolve_entry(service, 'guid-1', updated) is None


def test_resolve_entry_force_overwrite_ignores_freshness(service, stored):
    assert resolve_entry(service, 'guid-1', NOON - HOUR, force_overwrite=True) == stored


def test_resolve_entry_without_a_timestamp_skips_the_freshness_check(service, stored):
    assert resolve_entry(service, 'guid-1', None) == stored


def test_resolve_entry_never_rewrites_a_protected_entry(service, stored):
    stored.protected = True
    stored.save()

    assert resolve_entry(service, 'guid-1', NOON + HOUR, force_overwrite=True) is None


# --- ingest -------------------------------------------------------------------


@pytest.mark.django_db
def test_ingest_creates_a_new_entry(service):
    result = ingest(service, [candidate('new', content='Body')])

    assert result == ImportResult(created=1)
    e = Entry.objects.get(service=service, guid='new')
    assert (e.title, e.content) == ('Imported', 'Body')


def test_ingest_updates_only_the_fields_the_provider_set(service, stored):
    result = ingest(service, [candidate(title='Changed', date_updated=NOON + HOUR)])

    assert result == ImportResult(updated=1)
    stored.refresh_from_db()
    assert stored.title == 'Changed'
    assert stored.date_updated == NOON + HOUR
    assert (stored.author_name, stored.content) == ('Stored author', 'Stored content')


@pytest.mark.parametrize('protected', [False, True])
def test_ingest_skips_without_building(service, stored, protected):
    stored.protected = protected
    stored.save()
    freshness = NOON + HOUR if protected else NOON

    def build():
        raise AssertionError('a skipped candidate must not be built')

    result = ingest(service, [Candidate('guid-1', freshness, build)])

    assert result == ImportResult(skipped=1)
    stored.refresh_from_db()
    assert stored.title == 'Stored'


def test_ingest_force_overwrite_rewrites_an_unchanged_entry(service, stored):
    result = ingest(service, [candidate(freshness=NOON)], force_overwrite=True)

    assert result == ImportResult(updated=1)


@pytest.mark.django_db
def test_ingest_is_idempotent_for_a_repeated_payload(service):
    def batch():
        return [
            candidate(guid, freshness=NOON, date_updated=NOON) for guid in ('a', 'b')
        ]

    first = ingest(service, batch())
    again = ingest(service, batch())

    assert first == ImportResult(created=2)
    assert again == ImportResult(skipped=2)
    assert Entry.objects.filter(service=service).count() == 2


@pytest.mark.django_db
def test_ingest_registers_media_unless_told_not_to(service):
    ingest(service, [candidate('with', content='<img src="%s">' % THUMB)])
    ingest(
        service,
        [candidate('without', content='<img src="%s">' % THUMB, register_media=False)],
    )

    assert list(Media.objects.values_list('entry__guid', flat=True)) == ['with']


@pytest.mark.django_db
def test_ingest_reimport_keeps_media_and_entry_update(service):
    content = '<img src="%s">' % THUMB
    ingest(
        service, [candidate('m', freshness=NOON, content=content, date_updated=NOON)]
    )
    result = ingest(
        service,
        [candidate('m', freshness=NOON + HOUR, title='Again', content=content)],
    )

    assert result == ImportResult(updated=1)
    assert Entry.objects.get(guid='m').title == 'Again'
    assert Media.objects.filter(entry__guid='m').count() == 1


@pytest.mark.django_db
def test_ingest_rolls_back_an_entry_whose_media_cannot_be_stored(service):
    with patch(
        'glifestream.ingestion.service.media.extract_and_register',
        side_effect=RuntimeError('disk full'),
    ):
        result = ingest(service, [candidate('broken'), candidate('fine')])

    assert result.created == 0
    assert [guid for guid, _ in result.failed] == ['broken', 'fine']
    assert not Entry.objects.filter(service=service).exists()


@pytest.mark.django_db
def test_ingest_counts_a_failed_save_and_continues(service, caplog):
    bad = candidate('bad', date_published='not a date')
    result = ingest(service, [bad, candidate('good')])

    assert result.created == 1
    assert [guid for guid, _ in result.failed] == ['bad']
    assert 'Could not store entry bad' in caplog.text
    assert Entry.objects.filter(service=service, guid='good').exists()


@pytest.mark.django_db
def test_ingest_lets_a_mapping_error_propagate(service):
    def build():
        raise KeyError('title')

    with pytest.raises(KeyError):
        ingest(service, [Candidate('x', None, build)])


# --- types --------------------------------------------------------------------


def test_normalized_entry_reports_only_assigned_fields():
    e = NormalizedEntry('g', title='T')
    e.mblob = None

    assert e.author_name is UNSET
    assert e.assigned_fields() == {'title': 'T', 'mblob': None}
    assert repr(UNSET) == 'UNSET'


def test_import_results_add_up():
    a = ImportResult(created=1, skipped=2, failed=[('x', 'boom')])
    b = ImportResult(updated=3, failed=[('y', 'bang')])

    total = a + b

    assert total == ImportResult(
        created=1, updated=3, skipped=2, failed=[('x', 'boom'), ('y', 'bang')]
    )
    assert total.summary() == 'created=1 updated=3 skipped=2 failed=2'
