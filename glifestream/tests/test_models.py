import pytest
import datetime
from glifestream.stream.models import Media, WebSub, Entry

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


@pytest.mark.django_db
def test_media_model(service):
    entry = Entry.objects.create(
        service=service,
        title='Test Entry',
        guid='123',
        link='http://test.com',
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    media = Media.objects.create(entry=entry)
    assert media.entry == entry
    assert 'Test Entry' in str(media)


@pytest.mark.django_db
def test_websub_model(service):
    ws = WebSub.objects.create(
        service=service, hub='http://hub.com', hash='abcd1234abcd1234abcd'
    )
    assert ws.service == service
    assert ws.verified is False


@pytest.mark.django_db
def test_media_logic(service, settings, tmp_path):
    # Setup media root for test to avoid permission issues or cluttering real media
    settings.MEDIA_ROOT = str(tmp_path)
    # Mock storage to avoid actual filesystem interaction and settings issues
    from unittest.mock import MagicMock
    from django.core.files.storage import FileSystemStorage

    mock_storage = MagicMock(spec=FileSystemStorage)
    mock_storage.save.return_value = 'test.jpg'
    mock_storage.generate_filename.return_value = 'test.jpg'

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr('glifestream.stream.models.Media.file.field.storage', mock_storage)

        entry = Entry.objects.create(
            service=service,
            title='Media Entry',
            guid='m1',
            link='http://m.com',
            date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
        )
        from django.core.files.base import ContentFile

        m = Media(entry=entry)
        m.file.save('test.jpg', ContentFile(b'fake image data'))
        assert m.pk is not None
        # str(m) returns "EntryTitle: Filename"
        assert 'Media Entry: test.jpg' == str(m)
