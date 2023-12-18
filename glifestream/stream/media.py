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
from typing import Match

from django.conf import settings
from django.db.models.fields.files import FieldFile
from django.utils.encoding import force_bytes
from glifestream.stream.models import Media, Entry
from glifestream.stream.typing import ThumbInfo
from glifestream.utils import httpclient

try:
    from PIL import Image
except ImportError:
    try:
        import Image
    except ImportError:
        Image = None

logger = logging.getLogger(__name__)


def set_upload_url(s: str) -> str:
    return s.replace('[GLS-UPLOAD]/', settings.MEDIA_URL + 'upload/')


def set_thumbs_url(s: str) -> str:
    return re.sub(r'\[GLS-THUMBS\]/([a-f0-9])',
                  settings.MEDIA_URL + 'thumbs/\\1/\\1', s)


def get_thumb_hash(s: str) -> str | None:
    m = re.search(r'\[GLS-THUMBS\]/([a-f0-9]{40})', s)
    return m.groups()[0] if m else None


def get_thumb_info(thumb_hash: str, append_suffix: bool = False) -> ThumbInfo:
    prefix = thumb_hash[0] + '/'
    iformat = getattr(settings, 'APP_THUMBNAIL_FORMAT', 'JPEG')
    suffix = ''
    if append_suffix:
        if iformat.lower() == 'jpeg' or iformat.lower() == 'jpg':
            suffix = '.jpg'
        elif iformat.lower() == 'webp':
            suffix = '.webp'
        elif iformat.lower() == 'avif':
            suffix = '.avif'
        elif iformat.lower() == 'heif':
            suffix = '.heif'
    return {
        'format': iformat,
        'local': '%s/thumbs/%s%s%s' % (settings.MEDIA_ROOT, prefix, thumb_hash, suffix),
        'url': '%sthumbs/%s%s%s' % (settings.MEDIA_URL, prefix, thumb_hash, suffix),
        'rel': 'thumbs/%s%s%s' % (prefix, thumb_hash, suffix),
        'internal': '[GLS-THUMBS]/%s%s' % (thumb_hash, suffix),
    }


def save_image(url: str, direct_image=True, force=False, downscale=True,
               size: tuple[int, int] | None = None) -> str:
    if settings.BASE_URL in url:
        return url
    thumb = get_thumb_info(hashlib.sha1(force_bytes(url)).hexdigest())
    stale = False

    is_file = os.path.isfile(thumb['local'])
    if is_file and not direct_image:
        if (time.time() - os.path.getmtime(thumb['local'])) > 604800:
            is_file = False
            stale = True

    if not is_file:
        tmp = tempfile.mktemp('_gls')
        try:
            resp = httpclient.retrieve(url, tmp)
            if 'image/' not in resp.headers.get('content-type', ''):
                if not force and Image:
                    try:
                        Image.open(tmp)
                    except Exception:
                        os.remove(tmp)
                        return url
            if downscale:
                downscale_image(tmp, size=size, iformat=thumb['format'])
            shutil.move(tmp, thumb['local'])
        except Exception as exc:
            logger.error(exc)
            if not stale:
                return url
    return thumb['internal']


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
    url = '[GLS-UPLOAD]/%s' % file.name.replace('upload/', '')
    try:
        thumb = get_thumb_info(hashlib.sha1(file.name.encode('utf-8')).hexdigest())
        if not os.path.isfile(thumb['local']):
            shutil.copy(file.path, thumb['local'])
            downscale_image(thumb['local'], iformat=thumb['format'])
        return thumb['internal'], url
    except Exception as exc:
        logger.error(exc)
    return url, url


def extract_and_register(entry: Entry) -> None:
    for hash_thumb in re.findall(r'\[GLS-THUMBS\]/([a-f0-9]{40})', entry.content):
        md = Media(entry=entry)
        md.file.name = get_thumb_info(hash_thumb)['rel']
        try:
            md.save()
        except Exception as exc:
            logger.error(exc)


def __img_subs(m: Match[str]) -> str:
    return '<img%ssrc="%s"' % (m.group(1), save_image(m.group(2), force=True))


def transform_to_local(entry: Entry) -> None:
    entry.content = re.sub(
        r'<img(.*)src="(https?://.*?)"',
        __img_subs,
        entry.content,
        flags=re.DOTALL)


def mrss_init(mblob=None) -> dict:
    if mblob:
        if isinstance(mblob, str):
            mblob = json.loads(mblob)
        if 'content' in mblob:
            return mblob
    return {'content': []}


def mrss_scan(content: str) -> dict:
    # A limited solution.
    mblob = mrss_init()
    for v in re.findall(r'https?://www.youtube.com/watch\?v=([\-\w]+)', content):
        mblob['content'].append([{'url': 'https://www.youtube.com/v/' + v,
                                  'medium': 'video'}])
    for dummy, v in re.findall(r'https?://(www\.)?vimeo.com/(\d+)', content):
        mblob['content'].append([{'url': 'https://player.vimeo.com/video/' + v,
                                  'medium': 'video'}])
    return mblob


def mrss_gen_json(mblob) -> str | None:
    if len(mblob['content']):
        return json.dumps(mblob)
    return None


def mrss_gen_xml(entry: Entry) -> str:
    m = ''
    if entry.mblob:
        mblob = json.loads(entry.mblob)
        if 'content' in mblob:
            for g in mblob['content']:
                group = len(g) > 1
                if group:
                    m += '    <media:group>\n'
                for i in g:
                    for k in list(i.keys()):
                        if ':' in k:
                            del i[k]
                        if k == 'isdefault':
                            i['isDefault'] = i[k]
                            del i[k]
                        elif k == 'filesize':
                            i['fileSize'] = i[k]
                            del i[k]
                    attrs = ''.join([' %s="%s"' % (k, str(i[k])) for k in i])
                    if group:
                        m += '  '
                    m += '    <media:content%s/>\n' % attrs
                if group:
                    m += '    </media:group>\n'
            m = set_upload_url(set_thumbs_url(m))
    return m
