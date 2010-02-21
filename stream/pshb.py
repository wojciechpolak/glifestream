#  gLifestream Copyright (C) 2010 Wojciech Polak
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

import hmac
import hashlib
import urllib
import urllib2
from datetime import timedelta
from django.conf import settings
from django.core import urlresolvers
from glifestream.utils.time import now
from glifestream.stream.models import Pshb

def subscribe (service, verbose=False):
    try:
        webfeed = __import__ ('apis.webfeed', {}, {}, ['API'])
    except ImportError:
        return {'rc': 1, 'error': 'ImportError apis.webfeed'}
    webfeed_api = getattr (webfeed, 'API')

    try:
        mod = __import__ ('apis.%s' % service.api, {}, {}, ['API'])
    except ImportError:
        return {'rc': 1, 'error': 'ImportError apis.%s' % service.api}
    mod_api = getattr (mod, 'API')
    api = mod_api (service, False, False)

    if not isinstance (api, webfeed_api):
        return {'rc': 1, 'error': 'PSHB is not supported by this API.'}

    api.fetch_only = True
    api.run ()
    if api.fp_error:
        return {'rc': 1, 'error': api.fp.bozo_exception}

    hub = None
    for link in api.fp.feed.links:
        if link.rel == 'hub':
            hub = link.href
            break
    if not hub:
        return {'rc': 2}

    secret = hashlib.md5 ('%s:%d/%s/%s' % (hub, service.id, api.url,
                                           settings.SECRET_KEY)).hexdigest ()
    hash = hashlib.sha1 (secret).hexdigest ()[0:20]
    secret = secret[0:8] if 'https://' in hub else None

    save_db = False
    try:
        db = Pshb.objects.get (hash=hash, service=service)
    except Pshb.DoesNotExist:
        db = Pshb (hash=hash, service=service, hub=hub, secret=secret)
        save_db = True

    topic = settings.SITE_URL + urlresolvers.reverse ('index') + '?format=atom'
    callback = settings.SITE_URL + urlresolvers.reverse ('pshb', args=[hash])

    if settings.PSHB_HTTPS_CALLBACK:
        callback = callback.replace ('http://', 'https://')

    data = { 'hub.mode': 'subscribe',
             'hub.topic': topic,
             'hub.callback': callback,
             'hub.verify': 'async' }
    if secret:
        data['hub.secret'] = secret

    try:
        r = urllib2.urlopen (hub, urllib.urlencode (data))
        if verbose: print 'Response code: %d' % r.code
        if save_db: db.save ()
        return {'hub': hub, 'rc': r.code}
    except (IOError, urllib2.HTTPError), e:
        error = ''
        if hasattr (e, 'read'):
            error = e.read ()
        if verbose:
            print '%s, Response: "%s"' % (e, error)
        return {'hub': hub, 'rc': error}

def unsubscribe (id, verbose=False):
    try:
        db = Pshb.objects.get (id=id)
    except Pshb.DoesNotExist:
        return {'rc': 1}

    topic = settings.SITE_URL + urlresolvers.reverse ('index') + '?format=atom'
    callback = settings.SITE_URL + urlresolvers.reverse ('pshb', args=[db.hash])

    if settings.PSHB_HTTPS_CALLBACK:
        callback = callback.replace ('http://', 'https://')

    data = { 'hub.mode': 'unsubscribe',
             'hub.topic': topic,
             'hub.callback': callback,
             'hub.verify': 'sync' }

    try:
        r = urllib2.urlopen (db.hub, urllib.urlencode (data))
        if verbose: print 'Response code: %d' % r.code
        return {'hub': db.hub, 'rc': r.code}
    except (IOError, urllib2.HTTPError), e:
        error = ''
        if hasattr (e, 'read'):
            error = e.read ()
        if verbose:
            print '%s, Response: "%s"' % (e, error)
        return {'hub': db.hub, 'rc': error}

def verify (id, GET):
    mode = GET.get ('hub.mode', None)
    lease_seconds = GET.get ('hub.lease_seconds', None)

    if mode == 'subscribe':
        try:
            db = Pshb.objects.get (hash=id)
            db.verified = True
            if lease_seconds:
                db.expire = now () + timedelta (seconds=int(lease_seconds))
            db.save ()
        except Pshb.DoesNotExist:
            return False
    elif mode == 'unsubscribe':
        try:
            Pshb.objects.get (hash=id).delete ()
        except Pshb.DoesNotExist:
            return False

    return GET.get ('hub.challenge', '')

def publish (hubs=None, verbose=False):
    hubs = hubs or settings.PSHB_HUBS
    url = settings.SITE_URL + urlresolvers.reverse ('index') + '?format=atom'
    for hub in hubs:
        hub = hub.replace ('https://', 'http://') # it's just a ping.
        data = urllib.urlencode ({'hub.mode': 'publish', 'hub.url': url})
        try:
            r = urllib2.urlopen (hub, data, timeout=7)
            if verbose:
                if r.code == 204:
                    print '%s: Successfully pinged.' % hub
                else:
                    print '%s: Pinged and got %d.' % (hub, r.code)
        except (IOError, urllib2.HTTPError), e:
            if hasattr (e, 'code') and e.code == 204:
                continue
            if verbose:
                error = ''
                if hasattr (e, 'read'):
                    error = e.read ()
                print '%s, Response: "%s"' % (e, error)

def accept_payload (id, payload, meta={}):
    try:
        db = Pshb.objects.get (hash=id)
    except Pshb.DoesNotExist:
        return False
    if db.secret:
        s = hmac.new (str (db.secret), payload, hashlib.sha1).hexdigest ()
        signature = meta.get ('HTTP_X_HUB_SIGNATURE', None)
        if signature and 'sha1=' in signature:
            signature = signature[5:]
        if s != signature:
            return False # signature mismatch
    try:
        mod = __import__ ('apis.%s' % db.service.api, {}, {}, ['API'])
    except ImportError:
        return False
    mod_api = getattr (mod, 'API')
    api = mod_api (db.service, False, False)
    api.payload = payload
    api.run ()
    return True

def renew_subscriptions (force=False, verbose=False):
    subscriptions = Pshb.objects.all ().order_by ('id')
    for s in subscriptions:
        if s.expire:
            d = s.expire - timedelta (days=7)
            if now () > d or force:
                subscribe (s.service, verbose)

def list ():
    subscriptions = Pshb.objects.all ().order_by ('id')
    for s in subscriptions:
        print '%4d V=%d hash=%s, hub=%s, topic=%s, expire=%s' % \
            (s.id, s.verified, s.hash, s.hub, s.service.url, s.expire)
