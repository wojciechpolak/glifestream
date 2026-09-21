import os
import json
import time
from unittest.mock import patch, MagicMock

import pytest

from glifestream.stream import media
from glifestream.utils import httpclient


def test_set_upload_url():
    with patch('django.conf.settings.MEDIA_URL', '/media/'):
        res = media.set_upload_url('[GLS-UPLOAD]/test.jpg')
        assert res == '/media/upload/test.jpg'


def test_set_thumbs_url():
    with patch('django.conf.settings.MEDIA_URL', '/media/'):
        res = media.set_thumbs_url('[GLS-THUMBS]/a123.jpg')
        assert res == '/media/thumbs/a/a123.jpg'


def test_get_thumb_hash():
    assert media.get_thumb_hash('[GLS-THUMBS]/abc.jpg') == 'abc.jpg'
    assert media.get_thumb_hash('no thumb') is None


def test_get_thumb_info():
    with patch('django.conf.settings.MEDIA_URL', '/media/'):
        with patch('django.conf.settings.MEDIA_ROOT', '/root/media'):
            info = media.get_thumb_info('hash123', append_suffix=True)
            assert info['format'] == 'WEBP'
            assert info['local'] == '/root/media/thumbs/h/hash123.webp'
            assert info['url'] == '/media/thumbs/h/hash123.webp'


def test_mrss_scan():
    content = 'Check https://www.youtube.com/watch?v=vid1 and https://vimeo.com/123'
    mblob = media.mrss_scan(content)
    assert len(mblob['content']) == 2
    assert 'youtube.com/v/vid1' in mblob['content'][0][0]['url']
    assert 'player.vimeo.com/video/123' in mblob['content'][1][0]['url']


def test_mrss_gen_xml():
    from glifestream.stream.models import Entry

    mblob = {
        'content': [[{'url': 'http://vid.com', 'medium': 'video', 'isdefault': 'true'}]]
    }
    e = MagicMock(spec=Entry)
    e.mblob = json.dumps(mblob)

    with patch('django.conf.settings.MEDIA_URL', '/media/'):
        xml = media.mrss_gen_xml(e)
        assert (
            '<media:content url="http://vid.com" medium="video" isDefault="true"/>'
            in xml
        )


@patch('glifestream.stream.media.httpclient.retrieve')
@patch('shutil.move')
@patch('os.path.isfile')
def test_save_image_flow(mock_isfile, mock_move, mock_retrieve):
    # Case: file does not exist, download it
    mock_isfile.return_value = False

    def fake_retrieve(_url, filename, max_bytes=None, timeout=15):
        del max_bytes, timeout
        with open(filename, 'wb') as handle:
            handle.write(b'fake image data')
        return MagicMock(
            headers={'content-type': 'image/jpeg'},
            status_code=200,
            url='http://remote.com/img.jpg',
        )

    mock_retrieve.side_effect = fake_retrieve

    url = 'http://remote.com/img.jpg'
    with patch('django.conf.settings.BASE_URL', 'http://mysite.com'):
        # Mock Image if it exists or override downscale_image
        with patch('glifestream.stream.media.downscale_image'):
            image = MagicMock()
            image.verify.return_value = None
            image_open = MagicMock()
            image_open.return_value.__enter__.return_value = image
            with patch('glifestream.stream.media.Image.open', image_open):
                res = media.save_image(url)
                assert '[GLS-THUMBS]' in res
                mock_retrieve.assert_called_once()
                mock_move.assert_called_once()


def test_save_image_skip_local():
    url = 'http://mysite.com/img.jpg'
    with patch('django.conf.settings.BASE_URL', 'http://mysite.com'):
        res = media.save_image(url)
        assert res == url  # Skipped because it's local


def test_save_image_applies_file_upload_permissions(tmp_path):
    target = tmp_path / 'thumb.webp'
    thumb = {
        'format': 'WEBP',
        'local': str(target),
        'url': '/media/thumbs/a/thumb.webp',
        'rel': 'thumbs/a/thumb.webp',
        'internal': '[GLS-THUMBS]/thumb.webp',
    }

    def fake_retrieve(url, filename, max_bytes=None, timeout=15):
        del max_bytes, timeout
        with open(filename, 'wb') as handle:
            handle.write(b'fake image data')
        return MagicMock(
            headers={'content-type': 'image/jpeg'},
            status_code=200,
            url=url,
        )

    with patch('django.conf.settings.BASE_URL', 'http://mysite.com'):
        with patch('django.conf.settings.FILE_UPLOAD_PERMISSIONS', 0o644):
            with patch('glifestream.stream.media.get_thumb_info', return_value=thumb):
                with patch(
                    'glifestream.stream.media.httpclient.retrieve',
                    side_effect=fake_retrieve,
                ):
                    image = MagicMock()
                    image.verify.return_value = None
                    image_open = MagicMock()
                    image_open.return_value.__enter__.return_value = image
                    with patch('glifestream.stream.media.Image.open', image_open):
                        res = media.save_image(
                            'http://remote.com/img.jpg',
                            downscale=False,
                        )

    assert res == '[GLS-THUMBS]/thumb.webp'
    assert os.stat(target).st_mode & 0o777 == 0o644


def test_save_image_rejects_malformed_image_and_cleans_up(tmp_path):
    thumb = {
        'format': 'WEBP',
        'local': str(tmp_path / 'thumb.webp'),
        'url': '/media/thumbs/a/thumb.webp',
        'rel': 'thumbs/a/thumb.webp',
        'internal': '[GLS-THUMBS]/thumb.webp',
    }

    def fake_retrieve(_url, filename, max_bytes=None, timeout=15):
        del max_bytes, timeout
        with open(filename, 'wb') as handle:
            handle.write(b'not an image')
        return MagicMock(
            headers={'content-type': 'application/octet-stream'},
            status_code=200,
            url='http://remote.com/img.jpg',
        )

    with patch('django.conf.settings.BASE_URL', 'http://mysite.com'):
        with patch('glifestream.stream.media.get_thumb_info', return_value=thumb):
            with patch(
                'glifestream.stream.media.httpclient.retrieve',
                side_effect=fake_retrieve,
            ):
                with patch(
                    'glifestream.stream.media.Image.open',
                    side_effect=OSError('bad image'),
                ):
                    res = media.save_image('http://remote.com/img.jpg', downscale=False)

    assert res == 'http://remote.com/img.jpg'
    assert not os.path.exists(thumb['local'])


def test_save_image_returns_original_url_when_media_limit_is_hit(tmp_path):
    thumb = {
        'format': 'WEBP',
        'local': str(tmp_path / 'thumb.webp'),
        'url': '/media/thumbs/a/thumb.webp',
        'rel': 'thumbs/a/thumb.webp',
        'internal': '[GLS-THUMBS]/thumb.webp',
    }

    with patch('django.conf.settings.BASE_URL', 'http://mysite.com'):
        with patch('glifestream.stream.media.get_thumb_info', return_value=thumb):
            with patch(
                'glifestream.stream.media.httpclient.retrieve',
                side_effect=httpclient.build_fetch_error(
                    category='invalid_response',
                    detail='Media download from http://remote.com/img.jpg exceeds 10 bytes while streaming.',
                    retryable=False,
                    url='http://remote.com/img.jpg',
                ),
            ):
                res = media.save_image('http://remote.com/img.jpg', downscale=False)

    assert res == 'http://remote.com/img.jpg'


def test_save_image_keeps_stale_cached_thumb_when_refresh_fails(tmp_path):
    target = tmp_path / 'thumb.webp'
    target.write_bytes(b'stale')
    old_mtime = 1
    os.utime(target, (old_mtime, old_mtime))
    thumb = {
        'format': 'WEBP',
        'local': str(target),
        'url': '/media/thumbs/a/thumb.webp',
        'rel': 'thumbs/a/thumb.webp',
        'internal': '[GLS-THUMBS]/thumb.webp',
    }

    with patch('django.conf.settings.BASE_URL', 'http://mysite.com'):
        with patch('glifestream.stream.media.get_thumb_info', return_value=thumb):
            with patch(
                'glifestream.stream.media.httpclient.retrieve',
                side_effect=httpclient.build_fetch_error(
                    category='invalid_response',
                    detail='Media download from http://remote.com/img.jpg exceeds 10 bytes while streaming.',
                    retryable=False,
                    url='http://remote.com/img.jpg',
                ),
            ):
                with patch('time.time', return_value=604801 + old_mtime):
                    res = media.save_image(
                        'http://remote.com/img.jpg',
                        direct_image=False,
                        downscale=False,
                    )

    assert res == '[GLS-THUMBS]/thumb.webp'


def test_save_image_accepts_ambiguous_content_type_when_image_validation_succeeds(
    tmp_path,
):
    target = tmp_path / 'thumb.webp'
    thumb = {
        'format': 'WEBP',
        'local': str(target),
        'url': '/media/thumbs/a/thumb.webp',
        'rel': 'thumbs/a/thumb.webp',
        'internal': '[GLS-THUMBS]/thumb.webp',
    }

    def fake_retrieve(_url, filename, max_bytes=None, timeout=15):
        del max_bytes, timeout
        with open(filename, 'wb') as handle:
            handle.write(b'ambiguous image data')
        return MagicMock(
            headers={'content-type': 'application/octet-stream'},
            status_code=200,
            url='http://remote.com/img.jpg',
        )

    image = MagicMock()
    image.verify.return_value = None
    image_open = MagicMock()
    image_open.return_value.__enter__.return_value = image

    with patch('django.conf.settings.BASE_URL', 'http://mysite.com'):
        with patch('glifestream.stream.media.get_thumb_info', return_value=thumb):
            with patch(
                'glifestream.stream.media.httpclient.retrieve',
                side_effect=fake_retrieve,
            ):
                with patch('glifestream.stream.media.Image.open', image_open):
                    res = media.save_image('http://remote.com/img.jpg', downscale=False)

    assert res == '[GLS-THUMBS]/thumb.webp'
    assert os.path.exists(target)


def test_downsave_uploaded_image_applies_file_upload_permissions(tmp_path):
    source = tmp_path / 'upload.jpg'
    source.write_bytes(b'fake image data')
    os.chmod(source, 0o600)

    target = tmp_path / 'thumb.webp'
    thumb = {
        'format': 'WEBP',
        'local': str(target),
        'url': '/media/thumbs/a/thumb.webp',
        'rel': 'thumbs/a/thumb.webp',
        'internal': '[GLS-THUMBS]/thumb.webp',
    }
    field = MagicMock()
    field.name = 'upload/2026/04/07/upload.jpg'
    field.path = str(source)

    with patch('django.conf.settings.FILE_UPLOAD_PERMISSIONS', 0o644):
        with patch('glifestream.stream.media.get_thumb_info', return_value=thumb):
            with patch('glifestream.stream.media.downscale_image'):
                res = media.downsave_uploaded_image(field)

    assert res == ('[GLS-THUMBS]/thumb.webp', '[GLS-UPLOAD]/2026/04/07/upload.jpg')
    assert os.stat(target).st_mode & 0o777 == 0o644


def write_image(path, size=(1200, 900), mode='RGB'):
    from PIL import Image

    Image.new(mode, size, 'red').save(str(path))
    return path


def test_downscale_image_shrinks_an_oversized_picture(tmp_path):
    from PIL import Image

    path = write_image(tmp_path / 'big.jpg')

    media.downscale_image(str(path))

    with Image.open(str(path)) as im:
        assert im.size == (533, 400)


def test_downscale_image_leaves_a_small_picture_alone(tmp_path):
    from PIL import Image

    path = write_image(tmp_path / 'small.jpg', size=(320, 240))
    before = path.read_bytes()

    media.downscale_image(str(path))

    with Image.open(str(path)) as im:
        assert im.size == (320, 240)
    assert path.read_bytes() == before


def test_downscale_image_honours_an_explicit_size(tmp_path):
    from PIL import Image

    path = write_image(tmp_path / 'sized.jpg')

    media.downscale_image(str(path), size=(100, 100))

    with Image.open(str(path)) as im:
        assert max(im.size) == 100


def test_downscale_image_flattens_transparency_for_jpeg(tmp_path):
    from PIL import Image

    path = write_image(tmp_path / 'alpha.png', mode='RGBA')

    media.downscale_image(str(path), iformat='JPEG')

    with Image.open(str(path)) as im:
        assert im.mode == 'RGB'


def test_downscale_image_writes_the_format_it_was_given(tmp_path):
    from PIL import Image

    path = write_image(tmp_path / 'keep.png', mode='RGBA')

    media.downscale_image(str(path), iformat='WEBP')

    with Image.open(str(path)) as im:
        assert im.format == 'WEBP'
        assert im.size == (533, 400)


def test_downscale_image_swallows_an_unreadable_file(tmp_path):
    path = tmp_path / 'broken.jpg'
    path.write_bytes(b'not an image')

    media.downscale_image(str(path))

    assert path.read_bytes() == b'not an image'


def test_downscale_image_is_a_no_op_without_pillow(tmp_path):
    path = write_image(tmp_path / 'nopillow.jpg')
    before = path.read_bytes()

    with patch('glifestream.stream.media.Image', None):
        media.downscale_image(str(path))

    assert path.read_bytes() == before


@pytest.fixture
def cached_thumb(tmp_path, settings):
    settings.BASE_URL = 'http://mysite.com'
    thumb = {
        'format': 'WEBP',
        'local': str(tmp_path / 'thumb.webp'),
        'url': '/media/thumbs/a/thumb.webp',
        'rel': 'thumbs/a/thumb.webp',
        'internal': '[GLS-THUMBS]/thumb.webp',
    }
    with patch('glifestream.stream.media.get_thumb_info', return_value=thumb):
        yield thumb


def _age(path, seconds):
    then = time.time() - seconds
    os.utime(path, (then, then))


def test_save_image_serves_a_cached_image_without_fetching(cached_thumb):
    open(cached_thumb['local'], 'wb').close()
    _age(cached_thumb['local'], 30 * 24 * 3600)

    with patch('glifestream.stream.media.httpclient.retrieve') as retrieve:
        res = media.save_image('http://remote.com/img.jpg')

    assert res == '[GLS-THUMBS]/thumb.webp'
    retrieve.assert_not_called()


def test_save_image_serves_a_fresh_page_thumbnail_without_fetching(cached_thumb):
    open(cached_thumb['local'], 'wb').close()

    with patch('glifestream.stream.media.httpclient.retrieve') as retrieve:
        res = media.save_image('http://remote.com/page', direct_image=False)

    assert res == '[GLS-THUMBS]/thumb.webp'
    retrieve.assert_not_called()


def test_save_image_keeps_serving_a_stale_page_thumbnail_if_refetch_fails(
    cached_thumb, caplog
):
    open(cached_thumb['local'], 'wb').close()
    _age(cached_thumb['local'], 8 * 24 * 3600)

    with patch(
        'glifestream.stream.media.httpclient.retrieve',
        side_effect=RuntimeError('connection reset'),
    ) as retrieve:
        res = media.save_image('http://remote.com/page', direct_image=False)

    retrieve.assert_called_once()
    assert res == '[GLS-THUMBS]/thumb.webp'
    assert os.path.exists(cached_thumb['local'])
    assert 'connection reset' in caplog.text


def test_save_image_without_pillow_warns_only_when_forced(cached_thumb, caplog):
    def fake_retrieve(url, filename, **kwargs):
        with open(filename, 'wb') as handle:
            handle.write(b'data')
        return MagicMock(
            headers={'content-type': 'image/png'}, status_code=200, url=url
        )

    with (
        patch('glifestream.stream.media.Image', None),
        patch(
            'glifestream.stream.media.httpclient.retrieve', side_effect=fake_retrieve
        ),
    ):
        media.save_image('http://remote.com/a.png', downscale=False)
        assert 'Pillow unavailable' not in caplog.text
        os.remove(cached_thumb['local'])
        res = media.save_image('http://remote.com/a.png', downscale=False, force=True)

    assert res == '[GLS-THUMBS]/thumb.webp'
    assert 'Pillow unavailable' in caplog.text


@pytest.mark.parametrize(
    'iformat, suffix',
    [
        ('JPEG', '.jpg'),
        ('jpg', '.jpg'),
        ('AVIF', '.avif'),
        ('HEIF', '.heif'),
        ('PNG', ''),
    ],
)
def test_get_thumb_info_suffix_follows_the_format(settings, iformat, suffix):
    settings.APP_THUMBNAIL_FORMAT = iformat

    assert media.get_thumb_info('abc', append_suffix=True)['internal'] == (
        '[GLS-THUMBS]/abc' + suffix
    )
    assert media.get_thumb_info('abc', append_suffix=False)['internal'] == (
        '[GLS-THUMBS]/abc'
    )


def test_mrss_init():
    assert media.mrss_init() == {'content': []}
    assert media.mrss_init({'other': 1}) == {'content': []}
    assert media.mrss_init('{"content": [1]}') == {'content': [1]}
    blob = {'content': []}
    assert media.mrss_init(blob) is blob


def test_mrss_gen_xml_groups_several_items_and_drops_namespaced_keys():
    e = MagicMock(
        mblob=json.dumps(
            {
                'content': [
                    [{'url': 'a.mp4', 'filesize': 10, 'yt:x': 'drop'}],
                    [{'url': 'b.jpg'}, {'url': 'c.jpg'}],
                ]
            }
        )
    )

    assert media.mrss_gen_xml(e) == (
        '    <media:content url="a.mp4" fileSize="10"/>\n'
        '    <media:group>\n'
        '      <media:content url="b.jpg"/>\n'
        '      <media:content url="c.jpg"/>\n'
        '    </media:group>\n'
    )


def test_mrss_gen_xml_escapes_attribute_values():
    e = MagicMock(mblob=json.dumps({'content': [[{'url': 'https://e/x?a=1&b="2"<'}]]}))

    assert media.mrss_gen_xml(e) == (
        '    <media:content url="https://e/x?a=1&amp;b=&quot;2&quot;&lt;"/>\n'
    )


def test_mrss_gen_xml_without_media():
    assert media.mrss_gen_xml(MagicMock(mblob=None)) == ''
    assert media.mrss_gen_xml(MagicMock(mblob='{"other": 1}')) == ''
