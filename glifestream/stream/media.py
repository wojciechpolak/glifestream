#  gLifestream Copyright (C) 2009, 2010, 2013, 2014 Wojciech Polak
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
#  with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import re
import hashlib
import tempfile
import time
import types
import shutil
from django.conf import settings
from glifestream.stream.models import Media
from glifestream.utils import httpclient

try:
    import json
except ImportError:
    import simplejson as json

try:
    from PIL import Image
except ImportError:
    try:
        import Image
    except ImportError:
        Image = None


def set_upload_url(s):
    return s.replace('[GLS-UPLOAD]/', settings.MEDIA_URL + 'upload/')


def set_thumbs_url(s):
    return re.sub(r'\[GLS-THUMBS\]/([a-f0-9])',
                  settings.MEDIA_URL + 'thumbs/\\1/\\1', s)


def get_thumb_hash(s):
    m = re.search(r'\[GLS-THUMBS\]/([a-f0-9]{40})', s)
    return m.groups()[0] if m else None


def get_thumb_info(hash):
    prefix = hash[0] + '/'
    return {'local': '%s/thumbs/%s%s' % (settings.MEDIA_ROOT, prefix, hash),
            'url': '%sthumbs/%s%s' % (settings.MEDIA_URL, prefix, hash),
            'rel': 'thumbs/%s%s' % (prefix, hash),
            'internal': '[GLS-THUMBS]/%s' % hash, }


def save_image(url, direct_image=True, force=False, downscale=False,
               size=None):
    if settings.BASE_URL in url:
        return url
    thumb = get_thumb_info(hashlib.sha1(url).hexdigest())
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
            if not 'image/' in resp.headers.get('content-type', ''):
                if not force and Image:
                    try:
                        Image.open(tmp)
                    except:
                        os.remove(tmp)
                        return url
            if downscale:
                downscale_image(tmp, size=size)
            shutil.move(tmp, thumb['local'])
        except:
            if not stale:
                return url
    return thumb['internal']


def downscale_image(filename, size=None):
    if not Image:
        return
    size = size or (400, 175)
    try:
        im = Image.open(filename)
        w, h = im.size
        if w > size[0] or h > size[1]:
            im.thumbnail(size, Image.ANTIALIAS)
            im.save(filename, 'JPEG', quality=95)
    except:
        pass


def downsave_uploaded_image(file):
    url = '[GLS-UPLOAD]/%s' % file.name.replace('upload/', '')
    try:
        thumb = get_thumb_info(hashlib.sha1(file.name).hexdigest())
        if not os.path.isfile(thumb['local']):
            shutil.copy(file.path, thumb['local'])
            downscale_image(thumb['local'])
        return (thumb['internal'], url)
    except:
        pass
    return (url, url)


def extract_and_register(entry):
    for hash in re.findall(r'\[GLS-THUMBS\]/([a-f0-9]{40})', entry.content):
        md = Media(entry=entry)
        md.file.name = get_thumb_info(hash)['rel']
        try:
            md.save()
        except:
            pass


def __img_subs(m):
    return '<img src="%s"' % save_image(m.group(1), force=True)


def transform_to_local(entry):
    entry.content = re.sub(r'<img src="(http://.*?)"', __img_subs,
                           entry.content)


def mrss_init(mblob=None):
    if mblob:
        if isinstance (mblob, types.StringType) or \
           isinstance(mblob, types.UnicodeType):
            mblob = json.loads(mblob)
        if 'content' in mblob:
            return mblob
    return {'content': []}


def mrss_scan(content):
    # A limited solution.
    mblob = mrss_init()
    for v in re.findall(r'http://www.youtube.com/watch\?v=([\-\w]+)', content):
        mblob['content'].append([{'url': 'http://www.youtube.com/v/' + v,
                                  'type': 'application/x-shockwave-flash',
                                  'medium': 'video'}])
    for dummy, v in re.findall(r'http://(www\.)?vimeo.com/(\d+)', content):
        mblob[
            'content'].append([{'url': 'http://vimeo.com/moogaloop.swf?clip_id=' + v,
                                'type': 'application/x-shockwave-flash',
                                'medium': 'video'}])
    return mblob


def mrss_gen_json(mblob):
    if len(mblob['content']):
        return json.dumps(mblob)
    else:
        return None


def mrss_gen_xml(entry):
    m = ''
    if entry.mblob:
        mblob = json.loads(entry.mblob)
        if 'content' in mblob:
            for g in mblob['content']:
                group = True if len(g) > 1 else False
                if group:
                    m += '    <media:group>\n'
                for i in g:
                    for k in i.keys():
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
