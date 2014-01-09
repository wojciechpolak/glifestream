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

import urllib
from glifestream.utils import httpclient

try:
    import json
except ImportError:
    import simplejson as json

providers = {
    'flickr': 'www.flickr.com/services/oembed'
}


def discover(url, provider, maxwidth=None, maxheight=None):
    pro = providers.get(provider, None)
    if not pro:
        return None
    q = '?url=%s&format=json' % urllib.quote(url)
    if maxwidth:
        q += '&maxwidth=%d' % maxwidth
    if maxheight:
        q += '&maxheight=%d' % maxheight
    try:
        r = httpclient.urlopen(pro + q, timeout=15)
        if r.code == 200:
            return json.loads(r.data)
    except:
        pass
    return None
