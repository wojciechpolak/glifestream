import datetime
import json
import pytest
from unittest.mock import patch
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict
from glifestream.stream.models import Entry, Media, Service
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


def upload(name, content_type, payload=b'x' * 10):
    return SimpleUploadedFile(name, payload, content_type=content_type)


def docs(*files):
    uploads = MultiValueDict()
    uploads.setlist('docs', list(files))
    return uploads


@pytest.fixture
def selfposts(service):
    service.api = 'selfposts'
    service.save()
    return SelfpostsService(service)


@pytest.mark.django_db
def test_share_falls_back_to_the_raw_text_for_a_title(selfposts):
    entry = selfposts.share({'content': 'Just a sentence.'})

    assert entry is not None
    assert entry.title.startswith('Just a sentence')


@pytest.mark.django_db
def test_share_uses_the_configured_link_or_the_site_root(selfposts):
    # The guid is second-resolution, so the two posts need distinct clocks.
    with patch(
        'glifestream.apis.selfposts.utcnow',
        side_effect=[
            datetime.datetime(2026, 3, 22, 17, 0, 0, tzinfo=UTC),
            datetime.datetime(2026, 3, 22, 17, 0, 1, tzinfo=UTC),
        ],
    ):
        linked = selfposts.share({'content': 'A', 'link': 'https://elsewhere.example/'})
        default = selfposts.share({'content': 'B'})

    assert linked is not None and linked.link == 'https://elsewhere.example/'
    assert default is not None and default.link == settings.BASE_URL + '/'


@pytest.mark.django_db
def test_share_names_the_author_from_the_user(selfposts, user):
    user.first_name, user.last_name = 'Ada', 'Lovelace'
    user.save()

    entry = selfposts.share({'content': 'Signed', 'user': user})

    assert entry is not None
    assert entry.author_name == 'Ada Lovelace'


@pytest.mark.django_db
def test_share_renders_thumbnails_for_images_given_by_url(selfposts):
    with patch(
        'glifestream.apis.selfposts.media.save_image',
        side_effect=lambda url, **kw: url.replace('http', 'local'),
    ) as save_image:
        entry = selfposts.share(
            {
                'content': 'Look',
                'images': ['http://img.example/a.jpg', 'http://img.example/b.jpg'],
            }
        )

    assert entry is not None
    assert entry.content.count('class="thumbnails"') == 1
    assert 'local://img.example/a.jpg' in entry.content
    assert save_image.call_count == 2


@pytest.mark.django_db
def test_share_reports_a_post_it_could_not_save(selfposts, caplog):
    with patch.object(Entry, 'save', side_effect=Exception('db is upset')):
        assert selfposts.share({'content': 'Doomed'}) is None

    assert 'db is upset' in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    'name,expected_type',
    [
        ('photo.jpg', 'image/jpeg'),
        ('photo.JPEG', 'image/jpeg'),
        ('photo.webp', 'image/webp'),
        ('photo.avif', 'image/avif'),
        ('photo.heif', 'image/heif'),
    ],
)
def test_share_types_an_uploaded_picture_by_extension(selfposts, name, expected_type):
    with patch(
        'glifestream.apis.selfposts.media.downsave_uploaded_image',
        return_value=('thumb-' + name, name),
    ):
        entry = selfposts.share(
            {'content': 'With a picture', 'files': docs(upload(name, 'image/png'))}
        )

    assert entry is not None
    mblob = json.loads(entry.mblob)
    uploaded = mblob['content'][-1][0]
    assert uploaded['medium'] == 'image'
    assert uploaded['type'] == expected_type
    assert 'thumb-' + name in entry.content


@pytest.mark.django_db
def test_share_leaves_an_unknown_picture_type_unset(selfposts):
    with patch(
        'glifestream.apis.selfposts.media.downsave_uploaded_image',
        return_value=('thumb.png', 'photo.png'),
    ):
        entry = selfposts.share(
            {'content': 'Mystery', 'files': docs(upload('photo.png', 'image/png'))}
        )

    assert entry is not None
    uploaded = json.loads(entry.mblob)['content'][-1][0]
    assert uploaded['medium'] == 'image'
    assert 'type' not in uploaded


@pytest.mark.django_db
@pytest.mark.parametrize(
    'name,medium,expected_type',
    [
        ('song.mp3', 'audio', 'audio/mpeg'),
        ('song.ogg', 'audio', 'audio/ogg'),
        ('clip.mp4', 'video', 'video/mp4'),
        ('clip.webm', 'video', 'video/webm'),
        ('clip.avi', 'video', 'video/avi'),
        ('paper.pdf', 'document', 'application/pdf'),
    ],
)
def test_share_types_an_uploaded_file_by_extension(
    selfposts, name, medium, expected_type
):
    entry = selfposts.share(
        {'content': 'With a file', 'files': docs(upload(name, 'application/x-thing'))}
    )

    assert entry is not None
    uploaded = json.loads(entry.mblob)['content'][-1][0]
    assert uploaded['medium'] == medium
    assert uploaded['type'] == expected_type
    assert name in entry.content
    assert 'class="files"' in entry.content


@pytest.mark.django_db
def test_share_treats_an_unknown_upload_as_a_document(selfposts):
    entry = selfposts.share(
        {
            'content': 'Odd one',
            'files': docs(upload('notes.xyz', 'application/x-thing')),
        }
    )

    assert entry is not None
    uploaded = json.loads(entry.mblob)['content'][-1][0]
    assert uploaded['medium'] == 'document'
    assert 'type' not in uploaded


@pytest.mark.django_db
def test_share_handles_pictures_and_documents_together(selfposts):
    with patch(
        'glifestream.apis.selfposts.media.downsave_uploaded_image',
        return_value=('thumb.jpg', 'photo.jpg'),
    ):
        entry = selfposts.share(
            {
                'content': 'Both kinds',
                'files': docs(
                    upload('photo.jpg', 'image/jpeg'),
                    upload('paper.pdf', 'application/pdf'),
                ),
            }
        )

    assert entry is not None
    assert 'class="thumbnails"' in entry.content
    assert 'class="files"' in entry.content
    assert len(json.loads(entry.mblob)['content']) == 2


@pytest.mark.django_db
def test_share_targets_an_explicit_selfposts_service(selfposts):
    other = Service.objects.create(name='Photos', api='selfposts', cls='photos', url='')

    entry = selfposts.share({'content': 'Over there', 'sid': other.pk})

    assert entry is not None
    assert entry.service == other


@pytest.mark.django_db
def test_reshare_of_a_video_service_titles_the_entry(selfposts):
    vimeo = Service.objects.create(
        name='Vimeo', api='vimeo', url='someone', public=True
    )
    source = Entry.objects.create(
        service=vimeo,
        title='a vimeo clip',
        guid='reshare-video',
        link='https://vimeo.com/1',
        content='<div>player</div>',
        date_published=datetime.datetime(2026, 3, 22, 17, 0, tzinfo=UTC),
    )

    entry = selfposts.reshare(source, {})

    assert entry is not None
    assert entry.content.startswith('<p>A Vimeo Clip</p>')


@pytest.mark.django_db
def test_reshare_reports_a_post_it_could_not_save(selfposts, service, caplog):
    source = Entry.objects.create(
        service=service,
        title='Source',
        guid='reshare-doomed',
        link='http://example.com/',
        content='Body',
        date_published=datetime.datetime(2026, 3, 22, 17, 0, tzinfo=UTC),
    )

    with patch.object(Entry, 'save', side_effect=Exception('db is upset')):
        assert selfposts.reshare(source, {}) is None

    assert 'db is upset' in caplog.text


@pytest.mark.django_db
def test_reshare_registers_the_local_thumbnails(selfposts, service, caplog):
    source = Entry.objects.create(
        service=service,
        title='Source',
        guid='reshare-thumbs',
        link='http://example.com/',
        content='<img src="[GLS-THUMBS]/abcdef0123456789" alt="" />',
        date_published=datetime.datetime(2026, 3, 22, 17, 0, tzinfo=UTC),
    )

    entry = selfposts.reshare(source, {})

    assert entry is not None and entry.pk is not None
    assert list(Media.objects.filter(entry=entry).values_list('file', flat=True)) == [
        'thumbs/a/abcdef0123456789'
    ]
    assert caplog.records == []


@pytest.mark.django_db
def test_reshare_rolls_back_the_entry_when_media_fails(selfposts, service, caplog):
    source = Entry.objects.create(
        service=service,
        title='Source',
        guid='reshare-media-fails',
        link='http://example.com/',
        content='Body',
        date_published=datetime.datetime(2026, 3, 22, 17, 0, tzinfo=UTC),
    )

    with patch(
        'glifestream.apis.selfposts.media.extract_and_register',
        side_effect=Exception('thumbs unavailable'),
    ):
        assert selfposts.reshare(source, {}) is None

    assert 'thumbs unavailable' in caplog.text
    assert list(Entry.objects.values_list('guid', flat=True)) == ['reshare-media-fails']


def test_selfposts_service_has_no_feed_to_fetch(service):
    api = SelfpostsService(service)

    assert api.get_urls() == []
    assert api.run() is None
