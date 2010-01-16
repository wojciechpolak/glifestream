#  gLifestream Copyright (C) 2009, 2010 Wojciech Polak
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

from django.conf import settings
from django.template.defaultfilters import urlizetrunc, title as df_title
from django.utils.html import strip_tags
from glifestream.utils.time import mtime, utcnow
from glifestream.utils.html import strip_script
from glifestream.stream.models import Service, Entry
from glifestream.stream import media
from glifestream.filters import expand, truncate

try:
    import markdown
except ImportError:
    markdown = None

class API:
    name = 'Selfposts API'

    def __init__ (self, service, verbose = 0, force_overwrite = False):
        self.service = service
        self.verbose = verbose

    def run (self):
        pass

    def add (self, content, **args):
        id     = args.get ('id', None)
        title  = args.get ('title', None)
        link   = args.get ('link', None)
        images = args.get ('images', None)
        source = args.get ('source', '')

        un = utcnow ()
        guid = '%s/entry/%s' % (settings.FEED_TAGURI,
                                un.strftime ('%Y-%m-%dT%H:%M:%SZ'))
        if id:
            s = Service.objects.get (id=id, api='selfposts')
        else:
            s = Service.objects.filter (api='selfposts').order_by ('id')[0]
        e = Entry (service=s, guid=guid)

        e.link = link if link else settings.BASE_URL
        e.date_published = un
        e.date_updated = un

        if markdown and source != 'bookmarklet':
            e.content = expand.all (markdown.markdown (content))
        else:
            e.content = expand.all (content.replace ('\n', '<br/>'))
            e.content = urlizetrunc (e.content, 45)

        e.content = strip_script (e.content)
        e.content = expand.imgloc (e.content)

        if images:
            thumbs = '<div class="thumbnails">\n'
            for img in images:
                img = media.save_image (img, force=True, downscale=True)
                thumbs += """  <a href="%s" rel="nofollow"><img src="%s" alt="thumbnail" /></a>\n""" % (e.link, img)
            thumbs += '</div>'
            e.content += thumbs

        if title:
            e.title = title
        else:
            e.title = truncate.smart_truncate (strip_tags (e.content))
        if e.title == '':
            e.title = truncate.smart_truncate (strip_tags (content))

        try:
            e.save ()
            media.extract_and_register (e)
            return e
        except:
            pass

    def reshare (self, entry, id=None):
        un = utcnow ()
        guid = '%s/entry/%s' % (settings.FEED_TAGURI,
                                un.strftime ('%Y-%m-%dT%H:%M:%SZ'))
        if id:
            s = Service.objects.get (id=id, api='selfposts')
        else:
            s = Service.objects.filter (api='selfposts').order_by ('id')[0]
        e = Entry (service=s, guid=guid)

        e.link = entry.link
        e.author_name  = entry.author_name
        e.author_email = entry.author_email
        e.author_uri   = entry.author_uri
        e.date_published = un
        e.date_updated   = un

        e.geolat = entry.geolat
        e.geolng = entry.geolng

        e.title = entry.title
        if entry.service.api == 'greader':
            e.content = '<a href="%s" rel="nofollow">%s</a>' % (e.link, e.title)
        elif entry.service.api in ('youtube', 'vimeo'):
            e.content = '<p>%s</p>%s' % (df_title (e.title), entry.content)
        else:
            e.content = urlizetrunc (entry.content, 45)

        try:
            media.transform_to_local (e)
            media.extract_and_register (e)
            e.save ()
            return e
        except:
            pass

def filter_title (entry):
    return entry.title

def filter_content (entry):
    return entry.content
