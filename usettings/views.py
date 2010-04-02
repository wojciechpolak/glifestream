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

from django.conf import settings
from django.core import urlresolvers
from django.db import IntegrityError
from django.shortcuts import render_to_response
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.forms import ModelForm
from django.utils.translation import ugettext as _
from glifestream.stream.models import Service, List
from glifestream.auth import gls_openid
from glifestream.auth.models import OpenId
from glifestream.stream import pshb as gls_pshb
from glifestream.apis import API_LIST
from glifestream.utils import common

try:
    import json
except ImportError:
    import simplejson as json

@login_required
def services (request, **args):
    authed = request.user.is_authenticated () and request.user.is_staff
    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'themes': settings.THEMES,
        'themes_more': True if len (settings.THEMES) > 1 else False,
        'theme': common.get_theme (request),
        'title': _('Services - Settings'),
        'menu': 'services',
    }

    services = Service.objects.all ().order_by ('name')
    return render_to_response ('services.html',{ 'page': page, 'authed': authed,
                                                 'is_secure': request.is_secure (),
                                                 'user': request.user,
                                                 'services_supported': API_LIST,
                                                 'services': services })

class ListForm (ModelForm):
    class Meta:
        model = List
        exclude = ('user',)

@login_required
def lists (request, **args):
    authed = request.user.is_authenticated () and request.user.is_staff
    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'themes': settings.THEMES,
        'themes_more': True if len (settings.THEMES) > 1 else False,
        'theme': common.get_theme (request),
        'title': _('Lists - Settings'),
        'menu': 'lists',
    }
    curlist = ''
    lists = List.objects.filter (user=request.user).order_by ('name')

    if 'list' in args:
        try:
            list = List.objects.get (user=request.user, slug=args['list'])
            curlist = args['list']
        except List.DoesNotExist:
            list = List (user=request.user)
    else:
        list = List (user=request.user)

    if request.method == 'POST':
        if request.POST.get ('delete', False):
            list.delete ()
            return HttpResponseRedirect (
                urlresolvers.reverse ('glifestream.usettings.views.lists'))
        else:
            form = ListForm (request.POST, instance=list)
            if form.is_valid ():
                form.save ()
                return HttpResponseRedirect (
                    urlresolvers.reverse ('glifestream.usettings.views.lists',
                                          args=[list.slug]))
    else:
        form = ListForm (instance=list)

    return render_to_response ('lists.html',{ 'page': page, 'authed': authed,
                                              'is_secure': request.is_secure (),
                                              'user': request.user,
                                              'lists': lists,
                                              'curlist': curlist,
                                              'form': form })

@login_required
def pshb (request, **args):
    authed = request.user.is_authenticated () and request.user.is_staff
    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'themes': settings.THEMES,
        'themes_more': True if len (settings.THEMES) > 1 else False,
        'theme': common.get_theme (request),
        'title': _('PubSubHubbub - Settings'),
        'menu': 'pshb',
    }
    excluded_apis = ('selfposts', 'fb', 'friendfeed', 'twitter', 'vimeo')

    if request.POST.get ('subscribe', False):
        service = Service.objects.get (id=request.POST['subscribe'])
        r = gls_pshb.subscribe (service)
        if r['rc'] == 1:
            page['msg'] = r['error']
        elif r['rc'] == 2:
            page['msg'] = _('Hub not found.')
        elif r['rc'] == 202:
            page['msg'] = _('Hub %s: Accepted for verification.') % r['hub']
        elif r['rc'] == 204:
            page['msg'] = _('Hub %s: Subscription verified.') % r['hub']

    elif request.POST.get ('unsubscribe', False):
        r = gls_pshb.unsubscribe (request.POST['unsubscribe'])
        if r['rc'] == 1:
            page['msg'] = _('No subscription found.')
        elif r['rc'] == 202:
            page['msg'] = _('Hub %s: Accepted for verification.') % r['hub']
        elif r['rc'] == 204:
            page['msg'] = _('Hub %s: Unsubscribed.') % r['hub']
        else:
            page['msg'] = 'Hub %s: %s.' % (r['hub'], r['rc'])

    subs = gls_pshb.list (raw=True)
    services = Service.objects.exclude (api__in=excluded_apis) \
        .exclude (id__in=subs.values ('service__id')).order_by ('name')

    return render_to_response ('pshb.html',{ 'page': page, 'authed': authed,
                                             'is_secure': request.is_secure (),
                                             'user': request.user,
                                             'services': services,
                                             'subs': subs })

@login_required
def openid (request, **args):
    authed = request.user.is_authenticated () and request.user.is_staff
    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'themes': settings.THEMES,
        'themes_more': True if len (settings.THEMES) > 1 else False,
        'theme': common.get_theme (request),
        'title': _('OpenID - Settings'),
        'menu': 'openid',
    }

    openid_url = request.POST.get ('openid_identifier', None)
    if openid_url:
        rs = gls_openid.start (request, openid_url)
        if 'res' in rs:
            return rs['res']
        elif 'msg' in rs:
            page['msg'] = rs['msg']

    elif request.GET.get ('openid.mode', None):
        rs = gls_openid.finish (request)
        if 'identity_url' in rs:
            try:
                db = OpenId (user=request.user, identity=rs['identity_url'])
                db.save ()
                return HttpResponseRedirect (
                    urlresolvers.reverse ('glifestream.usettings.views.openid'))
            except IntegrityError:
                pass
        elif 'msg' in rs:
            page['msg'] = rs['msg']

    elif request.POST.get ('delete', None):
        try:
            OpenId (user=request.user,
                    id=int(request.POST.get ('delete'))).delete ()
        except:
            pass

    ids = OpenId.objects.filter (user=request.user).order_by ('identity')
    return render_to_response ('oid.html', { 'page': page, 'authed': authed,
                                             'is_secure': request.is_secure (),
                                             'user': request.user,
                                             'openids': ids })

#
# XHR API
#

def api (request, **args):
    cmd = args.get ('cmd', '')

    authed = request.user.is_authenticated () and request.user.is_staff
    if not authed:
        return HttpResponseForbidden ()

    method = request.POST.get ('method', 'get')
    id = request.POST.get ('id', None)

    # Add/edit services
    if cmd == 'service':
        s = {
            'api': request.POST.get ('api', ''),
            'name': request.POST.get ('name', ''),
            'cls': request.POST.get ('cls', ''),
            'url': request.POST.get ('url', ''),
            'display': request.POST.get ('display', 'content'),
            'public': bool (request.POST.get ('public', False)),
            'home': bool (request.POST.get ('home', False)),
            'active': bool (request.POST.get ('active', False)),
        }
        miss = {}

        # Data validation
        if method == 'post':
            if not s['name']:
                miss['name'] = True
                method = 'get'
            if s['api'] != 'selfposts' and not s['url'] \
               and request.POST.get ('timeline', 'user') == 'user':
                miss['url'] = True
                method = 'get'

        # Save
        if method == 'post':
            try:
                try:
                    if not id:
                        raise Service.DoesNotExist
                    srv = Service.objects.get (id=id)
                except Service.DoesNotExist:
                    srv = Service ()
                for k, v in s.items ():
                    setattr (srv, k, v)
            except:
                pass

            try:
                basic_user = request.POST.get ('basic_user', None)
                basic_pass = request.POST.get ('basic_pass', None)
                auth = request.POST.get ('auth', 'none')
                if auth == 'basic' and basic_user and basic_pass:
                    srv.creds = basic_user + ':' + basic_pass
                elif auth == 'oauth':
                    srv.creds = auth
                elif auth == 'none':
                    srv.creds = '';

                s['need_import'] = True if not srv.id else False
                srv.save ()
                id = srv.id
            except:
                pass

        # Get
        if id:
            try:
                srv = Service.objects.get (id=id)
                if not len (miss):
                    s.update ({
                        'id': srv.id,
                        'api': srv.api,
                        'name': srv.name,
                        'cls': srv.cls,
                        'url': srv.url,
                        'creds': srv.creds,
                        'display': srv.display,
                        'public': srv.public,
                        'home': srv.home,
                        'active': srv.active,
                    })
                else:
                    s['id'] = srv.id
                s['delete'] = _('delete')
            except Service.DoesNotExist:
                pass
        else:
            s['creds'] = ''
            s['home'] = True
            s['active'] = True

        # Setup fields
        s['fields'] = [
            {'type': 'text', 'name': 'name',
             'value': s['name'], 'label': _('Short name'),
             'miss': miss.get ('name', False)},
            {'type': 'text', 'name': 'cls',
             'value': s['cls'], 'label': _('Class name')}
        ]

        if s['api'] == 'webfeed':
            s['fields'].append ({'type': 'text', 'name': 'url',
                                 'value': s['url'], 'label': _('URL'),
                                 'miss': miss.get ('url', False)})

        elif s['api'] in ('fb', 'friendfeed', 'twitter', 'identica'):
            v = 'user' if s['url'] else 'home'
            s['fields'].append ({'type': 'select', 'name': 'timeline',
                                 'options': (('user', _('User timeline')),
                                             ('home', _('Home timeline'))),
                                 'value': v, 'label': _('Timeline')})
            s['fields'].append ({'type': 'text', 'name': 'url',
                                 'value': s['url'], 'label': _('ID/Username'),
                                 'deps': {'timeline': 'user'}})

        elif s['api'] != 'selfposts':
            s['fields'].append ({'type': 'text', 'name': 'url',
                                 'value': s['url'], 'label': _('ID/Username'),
                                 'miss': miss.get ('url', False)})

        if s['api'] in ('webfeed', 'twitter', 'friendfeed'):
            basic_user = ''
            if s['creds'] == 'oauth':
                v = 'oauth'
            elif s['creds']:
                v = 'basic'
                basic_user = s['creds'].split (':', 1)[0]
            else:
                v = 'none'

            s['fields'].append ({'type': 'select', 'name': 'auth',
                                 'options': (('none', _('none')),
                                             ('basic', _('Basic')),
                                             ('oauth', _('OAuth'))),
                                 'value': v, 'label': _('Authorization')})

            s['fields'].append ({'type': 'text', 'name': 'basic_user',
                                 'value': basic_user,
                                 'label': _('Basic username'),
                                 'deps': {'auth': 'basic'}})
            s['fields'].append ({'type': 'password', 'name': 'basic_pass',
                                 'value': '', 'label': _('Basic password'),
                                 'deps': {'auth': 'basic'}})

        if s['api'] == 'fb':
            s['fields'].append ({'type': 'text', 'name': 'creds',
                                 'value': s['creds'],
                                 'label': _('Session key')})

        if s['api'] in ('webfeed', 'flickr', 'youtube', 'vimeo'):
            s['fields'].append ({'type': 'select', 'name': 'display',
                                 'options': (('both', _('Title and Contents')),
                                             ('content', _('Contents only')),
                                             ('title', _('Title only'))),
                                 'value': s['display'],
                                 'label': _("Display entries'")})

        s['fields'].append ({'type': 'checkbox', 'name': 'public',
                             'checked': s['public'], 'label': _('Public'),
                             'hint': _('Public services are visible to anyone.')})

        s['fields'].append ({'type': 'checkbox', 'name': 'home',
                             'checked': s['home'], 'label': _('Home'),
                             'hint': _('If unchecked, this stream will be still active, but hidden and thus visible only via custom lists.')})

        if s['api'] != 'selfposts':
            s['fields'].append ({'type': 'checkbox', 'name': 'active',
                                 'checked': s['active'], 'label': _('Active'),
                                 'hint': _('If not active, this service will not be further updated.')})

        if 'creds' in s:
            del s['creds']

        s['action'] = request.build_absolute_uri ();
        s['save'] = _('Save')
        s['cancel'] = _('Cancel')

        #print json.dumps (s, indent=2)
        return HttpResponse (json.dumps (s), mimetype='application/json')

    # Import
    elif cmd == 'import' and id:
        try:
            service = Service.objects.get (id=id)
            mod = __import__ ('glifestream.apis.%s' % service.api, {}, {}, ['API'])
            mod_api = getattr (mod, 'API')
            api = mod_api (service, False, False)
            api.run ()
        except:
            pass

    return HttpResponse ()
