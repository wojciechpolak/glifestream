"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import pytest
from django.urls import reverse

from glifestream.stream.views import is_inline_media_type


@pytest.fixture
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    upload = tmp_path / 'upload'
    upload.mkdir()
    for name, body in {
        'a.png': b'\x89PNG\r\n\x1a\n',
        'a.svg': b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        'a.html': b'<p>x</p>',
        'a.pdf': b'%PDF-1.4',
        'a.mp3': b'ID3',
        'a.bin': b'x',
    }.items():
        (upload / name).write_bytes(body)
    return tmp_path


@pytest.mark.django_db
@pytest.mark.parametrize(
    'name, disposition',
    [
        ('a.png', 'inline'),
        ('a.pdf', 'inline'),
        ('a.mp3', 'inline'),
        ('a.svg', 'attachment'),
        ('a.html', 'attachment'),
        ('a.bin', 'attachment'),
    ],
)
def test_media_downloads_anything_a_browser_could_run(
    client, media_root, name, disposition
):
    response = client.get('/media/upload/%s' % name)
    response.close()

    assert response.status_code == 200
    assert response['Content-Disposition'] == '%s; filename="%s"' % (
        disposition,
        name,
    )
    assert response['X-Content-Type-Options'] == 'nosniff'


@pytest.mark.django_db
def test_media_answers_404_for_a_missing_file(client, media_root):
    assert client.get('/media/upload/missing.png').status_code == 404


@pytest.mark.parametrize(
    'content_type, inline',
    [
        ('image/jpeg', True),
        ('IMAGE/PNG', True),
        ('video/mp4', True),
        ('application/pdf', True),
        ('image/svg+xml', False),
        ('image/svg+xml; charset=utf-8', False),
        ('text/html; charset=utf-8', False),
        ('application/xhtml+xml', False),
        ('', False),
    ],
)
def test_is_inline_media_type(content_type, inline):
    assert is_inline_media_type(content_type) is inline


def test_media_url_is_routed():
    assert reverse('media', args=['upload/a.png']) == '/media/upload/a.png'
