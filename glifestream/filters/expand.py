#  gLifestream Copyright (C) 2009-2021 Wojciech Polak
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

import re
import hashlib
from urllib.parse import urlparse
from urllib.parse import parse_qsl
from django.utils.html import strip_tags
from glifestream.apis import vimeo
from glifestream.stream import media
from glifestream.utils import httpclient, oembed

#
# Short link services
#


def __su_subs(m):
    try:
        url = m.group(1) + m.group(2) + m.group(3)
        res = httpclient.head(url)
        return res.headers.get('location') or m.group(0)
    except Exception:
        return m.group(0)


def shorturls(text):
    """Expand short URLs."""
    return re.sub(r'(https?://)(tinyurl\.com|bit\.ly|goo\.gl|t\.co|is\.gd'
                  r'|ur1\.ca|2tu\.us|ff\.im|post\.ly|awe\.sm|lnk\.ms|pic\.gd'
                  r'|tl\.gd|youtu\.be|tiny\.cc|ow\.ly|j\.mp|url4\.eu'
                  r')(/[\-\w]+)', __su_subs, text)

#
# Short image services
#


def __gen_tai(link, img_src):
    return '<p class="thumbnails"><a href="%s" rel="nofollow"><img src="%s" alt="thumbnail" /></a></p>' % (link, img_src)


def __sp_twitpic(m):
    url = media.save_image('https://%s/show/full/%s' %
                           (m.group(2), m.group(3)), downscale=True)
    return __gen_tai(m.group(0), url)


def __sp_instagram(m):
    url = media.save_image('https://www.instagram.com/p/%s/media/?size=t' %
                           m.group(3), downscale=True)
    return __gen_tai(m.group(0), url)


def __sp_flickr(m):
    url = m.group(0)
    j = oembed.discover(url, provider='flickr', maxwidth=400)
    if j and j['type'] == 'photo':
        return __gen_tai(url, j['url'])
    return url


def __sp_imgloc(m):
    url = media.save_image(m.group(2))
    return '%s<p class="thumbnails"><img src="%s" alt="thumbnail" /></p>%s' % (m.group(1), url, m.group(4))


def shortpics(s):
    """Expand short picture-URLs."""
    s = re.sub(r'https?://(www\.)?(twitpic\.com)/(\w+)', __sp_twitpic, s)
    s = re.sub(r'https?://(instagr\.am)/p/([\w\-]+)/?', __sp_instagram, s)
    s = re.sub(
        r'https?://(www\.)?(instagram\.com)/p/([\w\-]+)/?', __sp_instagram, s)
    s = re.sub(r'https?://(www\.)?flickr\.com/([\w\.\-/]+)', __sp_flickr, s)
    return s


def imgloc(s):
    """Convert image location to html img."""
    s = re.sub(r'([^"])(https?://[\w\.\-\+/=%~]+\.(jpg|jpeg|png|gif))([^"])',
               __sp_imgloc, s)
    return s

#
# Video services
#


def __sv_youtube(m):
    if m.start() > 0 and m.string[m.start() - 1] == '"':
        return m.group(0)
    id_video = m.group(2)
    rest = m.group(3)
    ltag = rest.find('<') if rest else -1
    rest = rest[ltag:] if ltag != -1 else ''
    link = 'https://www.youtube.com/watch?v=%s' % id_video
    imgurl = 'https://i.ytimg.com/vi/%s/mqdefault.jpg' % id_video
    imgurl = media.save_image(imgurl, downscale=True, size=(320, 180))
    return '<table class="vc"><tr><td><div data-id="youtube-%s" class="play-video"><a href="%s" rel="nofollow">' \
           '<img src="%s" width="320" height="180" alt="YouTube Video" /></a><div class="playbutton">' \
           '</div></div></td></tr></table>%s' % (id_video, link, imgurl, rest)


def __sv_vimeo(m):
    if m.start() > 0 and m.string[m.start() - 1] == '"':
        return m.group(0)
    id_video = m.group(2)
    link = m.group(0)
    imgurl = vimeo.get_thumbnail_url(id_video)
    if imgurl:
        imgurl = media.save_image(imgurl, downscale=True, size=(320, 180))
        return '<table class="vc"><tr><td><div data-id="vimeo-%s" class="play-video"><a href="%s" rel="nofollow">' \
               '<img src="%s" width="320" height="180" alt="Vimeo Video" /></a>' \
               '<div class="playbutton"></div></div></td></tr></table>' % (
                   id_video, link, imgurl)
    return link


def __sv_dailymotion(m):
    link = strip_tags(m.group(0))
    id_video = m.group(1)
    rest = m.group(2)
    ltag = rest.find('<') if rest else -1
    rest = rest[ltag:] if ltag != -1 else ''
    imgurl = 'https://www.dailymotion.com/thumbnail/video/%s' % id_video
    imgurl = media.save_image(imgurl)
    return '<table class="vc"><tr><td><div data-id="dailymotion-%s" class="play-video"><a href="%s" rel="nofollow">' \
           '<img src="%s" width="320" height="180" alt="Dailymotion Video" />' \
           '</a><div class="playbutton"></div></div></td></tr></table>%s' % (
               id_video, link, imgurl, rest)


def videolinks(s):
    """Expand video links."""
    if 'youtube.com/' in s:
        s = re.sub(r'https?://(www\.)?youtube\.com/watch\?v=([\-\w]+)(\S*)',
                   __sv_youtube, s)
    if 'vimeo.com/' in s:
        s = re.sub(r'https?://(www\.)?vimeo\.com/(\d+)', __sv_vimeo, s)
    if 'dailymotion.com/' in s:
        s = re.sub(r'https?://www\.dailymotion\.com/video/([\-\w]+)(\S*)',
                   __sv_dailymotion, s)
    return s

#
# Audio services
#


def __sa_ogg(m):
    link = m.group(1)
    name = m.group(2)
    id_audio = hashlib.md5(link).hexdigest()
    return '<span data-id="audio-%s" class="play-audio"><a href="%s">%s</a></span>' % (id_audio, link, name)


def __sa_thesixtyone(m):
    link = m.group(0)
    songid = m.group(1)
    return '<span data-id="thesixtyone-art-%s" class="play-audio">' \
           '<a href="%s" rel="nofollow">%s</a></span>' % (songid, link, link)


def audiolinks(s):
    """Expand audio links."""
    if '.ogg' in s:
        s = re.sub(
            r'<a href="(https?://[\w\.\-\+/=%~]+\.ogg)">(.*?)</a>', __sa_ogg, s)
    if 'www.thesixtyone.com/' in s:
        # Scheme: http://www.thesixtyone.com/s/SONGID/
        s = re.sub(
            r'http://www.thesixtyone.com/s/(\w+)/', __sa_thesixtyone, s)
    return s

#
# Map services
#


def __parse_qs(qs, keep_blank_values=False, strict_parsing=False):
    d = {}
    for name, value in parse_qsl(qs, keep_blank_values, strict_parsing):
        d[name] = value
    return d


def __sm_googlemaps(m):
    link = strip_tags(m.group(0))
    rest = m.group(2)
    ltag = rest.find('<') if rest else -1
    rest = rest[ltag:] if ltag != -1 else ''
    params = __parse_qs(urlparse(link).query)
    ll = params.get('ll', None)
    if ll:
        ll = ll.split(',')
        geolat = float(ll[0])
        geolng = float(ll[1])
        return '<div class="geo"><a href="%s" class="map"><span class="latitude">%.10f</span> ' \
               '<span class="longitude">%.10f</span></a></div>%s' % (
                   link, geolat, geolng, rest)
    return link


def maplinks(s):
    """Expand map links."""
    if '//maps.google.' in s:
        s = re.sub(r'https?://maps.google.[a-z]{2,3}/(maps)?(\S*)',
                   __sm_googlemaps, s)
    return s

#
# Summary
#


def shorts(s):
    s = shorturls(s)
    return shortpics(s)


def run_all(s):
    s = shorturls(s)
    s = shortpics(s)
    s = audiolinks(s)
    s = videolinks(s)
    s = maplinks(s)
    return s
