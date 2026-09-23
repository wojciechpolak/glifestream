"""A thumbnail's life on disk, from download to orphan cleanup.

`test_stream_media.py` covers each media helper with the filesystem and the
network mocked out. These tests keep both real: a throwaway MEDIA_ROOT, real
images drawn with Pillow, and the real `httpclient`, mocked only at
`requests.get`. They follow a thumbnail from a provider's import, through
the Media rows that register it, to the maintenance jobs that later decide
whether it is still in use.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse
from PIL import Image

from glifestream.apis.factory import ServiceFactory
from glifestream.stream import media
from glifestream.stream.models import Entry, Favorite, Media, Service
from glifestream.worker import maintenance

DAY = 24 * 3600


def png(size: tuple[int, int] = (1200, 900)) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', size, 'red').save(buffer, 'PNG')
    return buffer.getvalue()


def thumb_rel(url: str) -> str:
    """Where `save_image` keeps the thumbnail of `url`, relative to MEDIA_ROOT."""
    thumb_hash = hashlib.sha1(url.encode()).hexdigest()
    return 'thumbs/%s/%s.jpg' % (thumb_hash[0], thumb_hash)


def internal(url: str) -> str:
    return '[GLS-THUMBS]/%s' % thumb_rel(url).rsplit('/', 1)[1]


def age(path: Path, seconds: float) -> None:
    then = time.time() - seconds
    os.utime(path, (then, then))


@pytest.fixture
def media_root(tmp_path: Path, settings) -> Path:
    """A MEDIA_ROOT laid out as `worker.py --init-files-dirs` leaves it."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.BASE_URL = 'https://gls.example'
    settings.APP_THUMBNAIL_FORMAT = 'JPEG'
    settings.FILE_UPLOAD_PERMISSIONS = 0o644
    for prefix in '0123456789abcdef':
        (tmp_path / 'thumbs' / prefix).mkdir(parents=True)
    (tmp_path / 'upload').mkdir()
    return tmp_path


class Remote:
    """Serves `requests.get`: images by URL, JSON for anything else asked."""

    def __init__(self) -> None:
        self.images: dict[str, bytes] = {}
        self.json: object = None
        self.fetched: list[str] = []

    def __call__(self, url: str, **kwargs) -> requests.Response:
        self.fetched.append(url)
        response = requests.Response()
        response.url = url
        if url in self.images:
            response.status_code = 200
            response.headers['content-type'] = 'image/png'
            response.raw = io.BytesIO(self.images[url])
        elif self.json is not None and not kwargs.get('stream'):
            response.status_code = 200
            response.headers['content-type'] = 'application/json'
            response._content = json.dumps(self.json).encode()
        else:
            response.status_code = 404
            response.raw = io.BytesIO(b'')
        return response


@pytest.fixture
def remote() -> Iterator[Remote]:
    serve = Remote()
    with patch('glifestream.utils.httpclient.requests.get', side_effect=serve):
        yield serve


_ids = itertools.count(1)


def status(*image_urls: str, avatar: str = 'https://social.example/avatar.png'):
    """A Mastodon status with one image attachment per URL."""
    status_id = str(next(_ids))
    return {
        'id': status_id,
        'created_at': '2026-01-0%sT12:00:00.000Z' % (int(status_id) % 9 + 1),
        'url': 'https://social.example/@me/%s' % status_id,
        'content': '<p>Status %s</p>' % status_id,
        'reblog': None,
        'account': {'display_name': 'Me', 'avatar_static': avatar},
        'media_attachments': [
            {
                'type': 'image',
                'url': url + '?full',
                'preview_url': url,
                'meta': {'small': {'width': 400, 'height': 300}},
            }
            for url in image_urls
        ],
    }


def import_mastodon(remote: Remote, *statuses, public: bool = True) -> Service:
    service = Service.objects.create(
        api='mastodon',
        name='Mastodon',
        url='https://social.example',
        user_id='1',
        public=public,
        active=True,
    )
    remote.json = list(statuses)
    ServiceFactory.create_service(service).run()
    return service


# ------------------------------------------------------------------ download


@pytest.mark.django_db
def test_imported_images_are_stored_as_downscaled_local_thumbnails(media_root, remote):
    picture = 'https://files.example/picture.png'
    remote.images[picture] = png((1200, 900))

    import_mastodon(remote, status(picture))

    entry = Entry.objects.get()
    assert internal(picture) in entry.content
    assert picture not in entry.content.replace(picture + '?full', '')
    with Image.open(media_root / thumb_rel(picture)) as stored:
        assert stored.format == 'JPEG'
        assert stored.size == (533, 400)
    assert os.stat(media_root / thumb_rel(picture)).st_mode & 0o777 == 0o644


@pytest.mark.django_db
def test_an_image_already_on_disk_is_not_downloaded_again(media_root, remote):
    picture = 'https://files.example/shared.png'
    remote.images[picture] = png()

    import_mastodon(remote, status(picture), status(picture))

    assert remote.fetched.count(picture) == 1
    assert Entry.objects.filter(content__contains=internal(picture)).count() == 2


@pytest.mark.django_db
def test_a_private_service_links_images_remotely(media_root, remote):
    picture = 'https://files.example/private.png'
    remote.images[picture] = png()

    import_mastodon(remote, status(picture), public=False)

    assert picture in Entry.objects.get().content
    assert picture not in remote.fetched
    assert not (media_root / thumb_rel(picture)).exists()


@pytest.mark.django_db
def test_an_image_that_fails_to_download_stays_remote(media_root, remote):
    missing = 'https://files.example/missing.png'

    import_mastodon(remote, status(missing))

    entry = Entry.objects.get()
    assert missing in entry.content
    assert not Media.objects.filter(entry=entry).exists()
    assert not any((media_root / 'thumbs').rglob('*.jpg'))


def test_transform_to_local_stores_every_remote_image(media_root, remote):
    first = 'https://files.example/one.png'
    second = 'https://files.example/two.png'
    remote.images[first] = png()
    remote.images[second] = png()
    entry = Entry(
        content='<p><img src="%s" alt="1" /> and <img alt="2" src="%s" /></p>'
        % (first, second)
    )

    media.transform_to_local(entry)

    assert entry.content == (
        '<p><img src="%s" alt="1" /> and <img alt="2" src="%s" /></p>'
        % (internal(first), internal(second))
    )
    assert (media_root / thumb_rel(first)).exists()
    assert (media_root / thumb_rel(second)).exists()


def test_transform_to_local_leaves_local_images_alone(media_root, remote):
    content = (
        '<img src="[GLS-THUMBS]/abc.jpg" /><img src="[GLS-UPLOAD]/2026/a.png" />'
        '<img src="https://gls.example/static/logo.png" />'
    )
    entry = Entry(content=content)

    media.transform_to_local(entry)

    assert entry.content == content
    assert remote.fetched == []


# -------------------------------------------------------------- registration


@pytest.mark.django_db
def test_imported_thumbnails_are_registered_once_per_entry(media_root, remote):
    picture = 'https://files.example/twice.png'
    remote.images[picture] = png()

    import_mastodon(remote, status(picture, picture))

    entry = Entry.objects.get()
    assert entry.content.count(internal(picture)) == 2
    assert list(Media.objects.filter(entry=entry).values_list('file', flat=True)) == [
        thumb_rel(picture)
    ]


@pytest.mark.django_db
def test_registering_again_keeps_the_enclosing_transaction_usable(service):
    entry = Entry.objects.create(
        service=service, guid='g', content='<img src="[GLS-THUMBS]/abc.jpg" />'
    )

    with transaction.atomic():
        media.extract_and_register(entry)
        media.extract_and_register(entry)
        # A failed INSERT without a savepoint would poison this transaction.
        assert Media.objects.filter(entry=entry).count() == 1


@pytest.mark.django_db
def test_favoriting_an_entry_stores_and_registers_its_images(
    media_root, remote, admin_client
):
    picture = 'https://files.example/favorite.png'
    remote.images[picture] = png()
    service = import_mastodon(remote, status(picture), public=False)
    entry = Entry.objects.get(service=service)

    response = admin_client.post(
        reverse('api', kwargs={'cmd': 'favorite'}), {'entry': entry.pk}
    )

    assert response.status_code == 200
    entry.refresh_from_db()
    assert Favorite.objects.filter(entry=entry).exists()
    assert internal(picture) in entry.content
    assert (media_root / thumb_rel(picture)).exists()
    assert Media.objects.filter(entry=entry, file=thumb_rel(picture)).exists()


# ------------------------------------------------------------------- uploads


@pytest.mark.django_db
def test_an_uploaded_picture_gets_a_downscaled_thumbnail(media_root, service):
    entry = Entry.objects.create(service=service, guid='upload')
    upload = Media(entry=entry)
    upload.file.save('photo.png', SimpleUploadedFile('photo.png', png((2000, 1000))))
    upload.save()
    name = upload.file.name
    assert name is not None

    thumb, original = media.downsave_uploaded_image(upload.file)

    assert original == '[GLS-UPLOAD]/%s' % name.removeprefix('upload/')
    thumb_hash = hashlib.sha1(name.encode()).hexdigest()
    assert thumb == '[GLS-THUMBS]/%s.jpg' % thumb_hash
    with Image.open(
        media_root / 'thumbs' / thumb_hash[0] / (thumb_hash + '.jpg')
    ) as im:
        assert im.size == (600, 300)
    with Image.open(upload.file.path) as im:
        assert im.size == (2000, 1000)


# ------------------------------------------------------------ orphan cleanup


def make_thumb(media_root: Path, rel: str, *, age_sec: float = 7 * DAY) -> str:
    path = media_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'thumb')
    age(path, age_sec)
    return rel


def run_maintenance(*args: str) -> None:
    maintenance.run_maintenance_args(list(args))


@pytest.mark.django_db
def test_orphans_appear_only_once_no_entry_uses_them(media_root, remote):
    shared = 'https://files.example/shared.png'
    own = 'https://files.example/own.png'
    remote.images.update({shared: png(), own: png()})
    service = import_mastodon(remote, status(shared, own), status(shared), public=True)
    for rel in (thumb_rel(shared), thumb_rel(own)):
        age(media_root / rel, 7 * DAY)
    assert maintenance.list_orphan_thumbs() == []

    Service.objects.filter(pk=service.pk).update(public=False)
    Entry.objects.filter(content__contains=internal(own)).update(
        date_published='2020-01-01T00:00Z', date_inserted='2020-01-01T00:00Z'
    )
    run_maintenance('--delete-old=30')
    run_maintenance('--thumbs-delete-orphans')

    assert not (media_root / thumb_rel(own)).exists()
    # The other entry still shows this one.
    assert (media_root / thumb_rel(shared)).exists()
    assert Media.objects.filter(file=thumb_rel(shared)).count() == 1


@pytest.mark.django_db
def test_a_thumbnail_downloaded_moments_ago_is_not_an_orphan_yet(media_root):
    # An import saves each thumbnail before it commits the entry that
    # shows it, so a cleanup run in between must not take the file.
    fresh = make_thumb(media_root, 'thumbs/a/a1.jpg', age_sec=60)
    stale = make_thumb(media_root, 'thumbs/b/b1.jpg', age_sec=2 * DAY)

    assert maintenance.list_orphan_thumbs() == [stale]
    run_maintenance('--thumbs-delete-orphans')

    assert (media_root / fresh).exists()
    assert not (media_root / stale).exists()


@pytest.mark.django_db
def test_deleting_orphans_survives_a_file_that_is_already_gone(media_root):
    gone = make_thumb(media_root, 'thumbs/a/a2.jpg')
    kept_going = make_thumb(media_root, 'thumbs/b/b2.jpg')
    os.remove(media_root / gone)

    maintenance.delete_thumb_files([gone, kept_going])

    assert not (media_root / kept_going).exists()


@pytest.mark.django_db
def test_a_thumbnail_in_the_wrong_directory_is_listed_where_it_is(media_root):
    # Thumbnails are served from thumbs/<first character>/, so a copy
    # anywhere else is unreachable, even if an entry names its hash.
    misplaced = make_thumb(media_root, 'thumbs/f/a3.jpg')

    assert maintenance.list_orphan_thumbs() == [misplaced]
    run_maintenance('--thumbs-delete-orphans')

    assert not (media_root / misplaced).exists()


@pytest.mark.django_db
def test_orphan_cleanup_leaves_uploads_alone(media_root):
    upload = media_root / 'upload' / 'photo.png'
    upload.write_bytes(png())
    age(upload, 7 * DAY)

    run_maintenance('--thumbs-delete-orphans')

    assert upload.exists()
