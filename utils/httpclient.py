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

import httplib
import urllib
import urllib2
from django.conf import settings

AGENT = 'Mozilla/5.0 (compatible; gLifestream; +%s/)' % settings.BASE_URL

class URLopener (urllib.FancyURLopener):
    version = AGENT

class HTTPError (urllib2.HTTPError):
    pass

def head (host, url, timeout=15):
    con = httplib.HTTPConnection (host, timeout=timeout)
    con.request ('HEAD', url)
    return con.getresponse ()

def get (host, url, headers={}, timeout=45):
    _headers = {'User-Agent': AGENT}
    _headers.update (headers)
    con = httplib.HTTPConnection (host, timeout=timeout)
    con.request ('GET', url, headers=_headers)
    return con.getresponse ()

def retrieve (url, filename):
    opener = URLopener ()
    return opener.retrieve (url, filename)[1]

def urlopen (url, data=None, headers={}, timeout=45):
    _headers = {'User-Agent': AGENT}
    _headers.update (headers)
    if not url.startswith ('http'):
        url = 'http://' + url
    if data:
        data = urllib.urlencode (data)
    req = urllib2.Request (url, data, _headers)
    try:
        return urllib2.urlopen (req, timeout=timeout)
    except urllib2.HTTPError, e:
        raise HTTPError (e.url, e.code, e.msg, e.hdrs, e.fp)
