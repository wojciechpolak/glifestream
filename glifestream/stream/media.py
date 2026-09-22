"""
#  gLifestream Copyright (C) 2009, 2010, 2013, 2014, 2015, 2023 Wojciech Polak
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

import os
import re
import json
import logging
import hashlib
import tempfile
import time
import shutil
from typing import Match, cast
from xml.sax.saxutils import escape as xml_escape

from django.conf import settings
from django.db import transaction
from django.db.models.fields.files import FieldFile
from django.utils.encoding import force_bytes
from glifestream.stream.models import Media, Entry
from glifestream.stream.typing import ThumbInfo
from glifestream.utils import httpclient

try:
    from PIL import Image
except ImportError:
    try:
        import Image  # type: ignore
    except ImportError:
        Image = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def apply_media_permissions(filename: str) -> None:
    mode = getattr(settings, 'FILE_UPLOAD_PERMISSIONS', None)
    if mode is None:
        return
    try:
        os.chmod(filename, mode)
    except OSError as exc:
        logger.error(exc)


def set_upload_url(s: str) -> str:
    return s.replace('[GLS-UPLOAD]/', settings.MEDIA_URL + 'upload/')


def set_thumbs_url(s: str) -> str:
    return re.sub(
        r'\[GLS-THUMBS\]/([a-f0-9])([a-z0-9\.]+)',
        settings.MEDIA_URL + 'thumbs/\\1/\\1\\2',
        s,
    )


def get_thumb_hash(s: str) -> str | None:
    m = re.search(r'\[GLS-THUMBS\]/([a-z0-9\.]+)', s)
    return m.groups()[0] if m else None


_THUMB_SUFFIXES = {
    'jpeg': '.jpg',
    'jpg': '.jpg',
    'webp': '.webp',
    'avif': '.avif',
    'heif': '.heif',
}

# A cached thumbnail of a page (rather than of an image URL) is refetched
# once it is older than this.
_PAGE_THUMB_MAX_AGE_SEC = 7 * 24 * 3600


def get_thumb_info(thumb_hash: str, append_suffix: bool) -> ThumbInfo:
    prefix = thumb_hash[0] + '/'
    iformat = getattr(settings, 'APP_THUMBNAIL_FORMAT', 'JPEG')
    suffix = _THUMB_SUFFIXES.get(iformat.lower(), '') if append_suffix else ''
    return {
        'format': iformat,
        'local': '%s/thumbs/%s%s%s' % (settings.MEDIA_ROOT, prefix, thumb_hash, suffix),
        'url': '%sthumbs/%s%s%s' % (settings.MEDIA_URL, prefix, thumb_hash, suffix),
        'rel': 'thumbs/%s%s%s' % (prefix, thumb_hash, suffix),
        'internal': '[GLS-THUMBS]/%s%s' % (thumb_hash, suffix),
    }


def save_image(
    url: str,
    direct_image=True,
    force=False,
    downscale=True,
    size: tuple[int, int] | None = None,
) -> str:
    """Cache a remote image as a local thumbnail and return its internal URL.

    Falls back to the remote `url` when the download fails and there is no
    earlier copy to keep serving.
    """
    if settings.BASE_URL in url:
        return url
    thumb_id = hashlib.sha1(force_bytes(url)).hexdigest()
    thumb = get_thumb_info(thumb_id, append_suffix=True)

    cached, stale = _cached_thumb(thumb['local'], direct_image)
    if cached:
        return thumb['internal']
    try:
        _download_thumb(url, thumb, force=force, downscale=downscale, size=size)
    except Exception as exc:
        _log_rejected_media(url, exc)
        if not stale:
            return url
    return thumb['internal']


def _cached_thumb(path: str, direct_image: bool) -> tuple[bool, bool]:
    """(usable, stale): whether a cached copy can be served as-is, and
    whether an expired copy exists to fall back on if refetching fails."""
    if not os.path.isfile(path):
        return False, False
    if not direct_image:
        if time.time() - os.path.getmtime(path) > _PAGE_THUMB_MAX_AGE_SEC:
            return False, True
    return True, False


def _download_thumb(
    url: str,
    thumb: ThumbInfo,
    *,
    force: bool,
    downscale: bool,
    size: tuple[int, int] | None,
) -> None:
    fd, tmp = tempfile.mkstemp(suffix='_gls')
    os.close(fd)
    try:
        resp = httpclient.retrieve(url, tmp)
        httpclient.validate_media_response(resp)
        _verify_image(tmp, url, resp, force=force)
        if downscale:
            downscale_image(tmp, size=size, iformat=thumb['format'])
        shutil.move(tmp, thumb['local'])
        apply_media_permissions(thumb['local'])
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _verify_image(path: str, url: str, resp, *, force: bool) -> None:
    if not Image:
        if force:
            logger.warning('Pillow unavailable while validating remote media: %s', url)
        return
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        raise httpclient.build_fetch_error(
            category='invalid_response',
            detail='Media download from %s could not be validated as an image: %s'
            % (url, exc),
            retryable=False,
            status_code=resp.status_code,
            url=resp.url,
        ) from exc


def _log_rejected_media(url: str, exc: Exception) -> None:
    if isinstance(exc, httpclient.FetchError):
        logger.warning(
            'Rejected remote media %s: %s (%s)', url, exc.category, exc.detail
        )
    else:
        logger.error(exc)


def downscale_image(filename: str, size=None, iformat='JPEG') -> None:
    if not Image:
        return
    size = size or (600, 400)
    try:
        with Image.open(filename) as im:
            if iformat.lower() == 'jpeg' or iformat.lower() == 'jpg':
                im = im.convert('RGB')
            w, h = im.size
            if w > size[0] or h > size[1]:
                im.thumbnail(size, Image.LANCZOS)
                im.save(filename, iformat, quality=95)
    except Exception as exc:
        logger.error(exc)


def downsave_uploaded_image(file: FieldFile) -> tuple[str, str]:
    if file.name is None:
        return '', ''
    url = file.name.replace('upload/', '')
    if url is not None:
        url = '[GLS-UPLOAD]/%s' % url
    try:
        if file.name is not None:
            thumb_id = hashlib.sha1(file.name.encode('utf-8')).hexdigest()
            thumb = get_thumb_info(thumb_id, append_suffix=True)
            if not os.path.isfile(thumb['local']):
                shutil.copy(file.path, thumb['local'])
                downscale_image(thumb['local'], iformat=thumb['format'])
                apply_media_permissions(thumb['local'])
            return thumb['internal'], url
    except Exception as exc:
        logger.error(exc)
    return url, url


def extract_and_register(entry: Entry) -> None:
    """Create a Media row for each thumbnail in the content that lacks one."""
    registered: set[str] = set()
    if entry.pk is not None:
        registered.update(
            Media.objects.filter(entry=entry).values_list('file', flat=True)
        )
    for hash_thumb in re.findall(r'\[GLS-THUMBS\]/([a-z0-9\.]+)', entry.content):
        rel = get_thumb_info(hash_thumb, append_suffix=False)['rel']
        if rel in registered:
            continue
        registered.add(rel)
        md = Media(entry=entry)
        md.file.name = rel
        try:
            # The savepoint keeps a duplicate thumbnail from breaking an
            # enclosing transaction, such as the one ingest() opens per entry.
            with transaction.atomic():
                md.save()
        except Exception as exc:
            logger.error(exc)


def __img_subs(m: Match[str]) -> str:
    return '<img%ssrc="%s"' % (m.group(1), save_image(m.group(2), force=True))


def transform_to_local(entry: Entry) -> None:
    entry.content = re.sub(
        r'<img(.*)src="(https?://.*?)"', __img_subs, entry.content, flags=re.DOTALL
    )


def mrss_init(mblob=None) -> dict:
    if mblob:
        if isinstance(mblob, str):
            mblob = json.loads(mblob)
        if 'content' in mblob:
            return cast(dict, mblob)
    return {'content': []}


def mrss_scan(content: str) -> dict:
    # A limited solution.
    mblob = mrss_init()
    for v in re.findall(r'https?://www.youtube.com/watch\?v=([\-\w]+)', content):
        mblob['content'].append(
            [{'url': 'https://www.youtube.com/v/' + v, 'medium': 'video'}]
        )
    for dummy, v in re.findall(r'https?://(www\.)?vimeo.com/(\d+)', content):
        mblob['content'].append(
            [{'url': 'https://player.vimeo.com/video/' + v, 'medium': 'video'}]
        )
    return mblob


def mrss_gen_json(mblob) -> str | None:
    if len(mblob['content']):
        return json.dumps(mblob)
    return None


# Lower-case keys stored in mblobs that Media RSS spells in camel case.
_MRSS_ATTR_RENAMES = {'isdefault': 'isDefault', 'filesize': 'fileSize'}


def mrss_gen_xml(entry: Entry) -> str:
    if not entry.mblob:
        return ''
    mblob = json.loads(entry.mblob)
    m = ''.join(_mrss_group_xml(group) for group in mblob.get('content', ()))
    return set_upload_url(set_thumbs_url(m))


def _mrss_group_xml(group: list[dict]) -> str:
    if len(group) <= 1:
        return ''.join('    <media:content%s/>\n' % _mrss_attrs(i) for i in group)
    items = ''.join('      <media:content%s/>\n' % _mrss_attrs(i) for i in group)
    return '    <media:group>\n%s    </media:group>\n' % items


def _mrss_attrs(item: dict) -> str:
    """The item as XML attributes, dropping namespaced keys.

    Renamed keys are emitted last, the order this function has always used.
    """
    plain = [
        (k, v) for k, v in item.items() if ':' not in k and k not in _MRSS_ATTR_RENAMES
    ]
    renamed = [
        (_MRSS_ATTR_RENAMES[k], v) for k, v in item.items() if k in _MRSS_ATTR_RENAMES
    ]
    return ''.join(
        ' %s="%s"' % (k, xml_escape(str(v), {'"': '&quot;'}))
        for k, v in plain + renamed
    )
