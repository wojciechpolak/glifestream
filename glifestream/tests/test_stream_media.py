import os
import json
from unittest.mock import patch, MagicMock
from glifestream.stream import media


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
    mock_retrieve.return_value = MagicMock(headers={'content-type': 'image/jpeg'})

    url = 'http://remote.com/img.jpg'
    with patch('django.conf.settings.BASE_URL', 'http://mysite.com'):
        # Mock Image if it exists or override downscale_image
        with patch('glifestream.stream.media.downscale_image'):
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

    def fake_retrieve(url, filename):
        with open(filename, 'wb') as handle:
            handle.write(b'fake image data')
        return MagicMock(headers={'content-type': 'image/jpeg'})

    with patch('django.conf.settings.BASE_URL', 'http://mysite.com'):
        with patch('django.conf.settings.FILE_UPLOAD_PERMISSIONS', 0o644):
            with patch('glifestream.stream.media.get_thumb_info', return_value=thumb):
                with patch(
                    'glifestream.stream.media.httpclient.retrieve',
                    side_effect=fake_retrieve,
                ):
                    res = media.save_image('http://remote.com/img.jpg', downscale=False)

    assert res == '[GLS-THUMBS]/thumb.webp'
    assert os.stat(target).st_mode & 0o777 == 0o644


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
