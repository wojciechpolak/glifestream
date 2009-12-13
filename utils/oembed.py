#  gLifestream Copyright (C) 2009 Wojciech Polak
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

import httplib
import urllib

try:
    import json
except ImportError:
    import simplejson as json

providers = {
    'flickr': ('www.flickr.com', '/services/oembed')
}

def discover (url, provider, maxwidth=None, maxheight=None):
    p = providers.get (provider, None)
    if not p:
        return None
    q = '%s?url=%s&format=json' % (p[1], urllib.quote (url))
    if maxwidth:
        q += '&maxwidth=%d' % maxwidth
    if maxheight:
        q += '&maxheight=%d' % maxheight
    try:
        conn = httplib.HTTPConnection (p[0])
        conn.request ('GET', q)
        response = conn.getresponse ()
        if response.status == 200:
            return json.loads (response.read ())
    except Exception:
        pass
    return None
