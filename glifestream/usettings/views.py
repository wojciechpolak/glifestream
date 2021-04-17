#  gLifestream Copyright (C) 2010, 2011, 2014, 2015 Wojciech Polak
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
from django.conf import settings
from django.urls import reverse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.forms import ModelForm
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from glifestream.stream.models import Service, List
from glifestream.gauth import gls_oauth
from glifestream.stream import pshb as gls_pshb
from glifestream.apis import API_LIST
from glifestream.utils import common


@login_required
@never_cache
def services(request, **args):
    authed = request.user.is_authenticated and request.user.is_staff
    if not authed:
        return HttpResponseForbidden()

    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'favicon': settings.FAVICON,
        'themes': settings.THEMES,
        'themes_more': len(settings.THEMES) > 1,
        'theme': common.get_theme(request),
        'title': _('Services - Settings'),
        'menu': 'services',
    }

    services_all = Service.objects.all().order_by('api', 'name')
    return render(request, 'services.html',
                  {'page': page, 'authed': authed,
                   'is_secure': request.is_secure(),
                   'user': request.user,
                   'services_supported': API_LIST,
                   'services': services_all})


class ListForm (ModelForm):

    class Meta:
        model = List
        exclude = ('user',)


@login_required
def lists(request, **args):
    authed = request.user.is_authenticated and request.user.is_staff
    if not authed:
        return HttpResponseForbidden()

    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'favicon': settings.FAVICON,
        'themes': settings.THEMES,
        'themes_more': len(settings.THEMES) > 1,
        'theme': common.get_theme(request),
        'title': _('Lists - Settings'),
        'menu': 'lists',
    }
    curlist = ''
    lists_user = List.objects.filter(user=request.user).order_by('name')

    if 'list' in args:
        try:
            list_user = List.objects.get(user=request.user, slug=args['list'])
            curlist = args['list']
        except List.DoesNotExist:
            list_user = List(user=request.user)
    else:
        list_user = List(user=request.user)

    if request.method == 'POST':
        if request.POST.get('delete', False):
            list_user.delete()
            return HttpResponseRedirect(reverse('usettings-lists'))
        form = ListForm(request.POST, instance=list_user)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('usettings-lists-slug',
                                        args=[list_user.slug]))
    else:
        form = ListForm(instance=list_user)

    return render(request, 'lists.html',
                  {'page': page,
                   'authed': authed,
                   'is_secure': request.is_secure(),
                   'user': request.user,
                   'lists': lists_user,
                   'curlist': curlist,
                   'form': form})


@login_required
def pshb(request, **args):
    authed = request.user.is_authenticated and request.user.is_staff
    if not authed:
        return HttpResponseForbidden()

    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'favicon': settings.FAVICON,
        'themes': settings.THEMES,
        'themes_more': len(settings.THEMES) > 1,
        'theme': common.get_theme(request),
        'title': _('PubSubHubbub - Settings'),
        'menu': 'pshb',
    }
    excluded_apis = ('selfposts', 'fb', 'friendfeed', 'twitter', 'vimeo')

    if request.POST.get('subscribe', False):
        service = Service.objects.get(id=request.POST['subscribe'])
        r = gls_pshb.subscribe(service)
        if r['rc'] == 1:
            page['msg'] = r['error']
        elif r['rc'] == 2:
            page['msg'] = _('Hub not found.')
        elif r['rc'] == 202:
            page['msg'] = _('Hub %s: Accepted for verification.') % r['hub']
        elif r['rc'] == 204:
            page['msg'] = _('Hub %s: Subscription verified.') % r['hub']

    elif request.POST.get('unsubscribe', False):
        r = gls_pshb.unsubscribe(request.POST['unsubscribe'])
        if r['rc'] == 1:
            page['msg'] = _('No subscription found.')
        elif r['rc'] == 202:
            page['msg'] = _('Hub %s: Accepted for verification.') % r['hub']
        elif r['rc'] == 204:
            page['msg'] = _('Hub %s: Unsubscribed.') % r['hub']
        else:
            page['msg'] = 'Hub %s: %s.' % (r['hub'], r['rc'])

    subs = gls_pshb.list_subs(raw=True)
    services = Service.objects.exclude(api__in=excluded_apis) \
        .exclude(id__in=subs.values('service__id')).order_by('name')

    return render(request, 'pshb.html',
                  {'page': page,
                   'authed': authed,
                   'is_secure': request.is_secure(),
                   'user': request.user,
                   'services': services,
                   'subs': subs})


@login_required
def tools(request, **args):
    authed = request.user.is_authenticated and request.user.is_staff
    page = {
        'robots': 'noindex',
        'base_url': settings.BASE_URL,
        'favicon': settings.FAVICON,
        'themes': settings.THEMES,
        'themes_more': len(settings.THEMES) > 1,
        'theme': common.get_theme(request),
        'title': _('Tools'),
        'menu': 'tools',
    }
    return render(request, 'tools.html',
                  {'page': page, 'authed': authed,
                   'is_secure': request.is_secure(),
                   'user': request.user})


@login_required
@never_cache
def oauth(request, **args):
    authed = request.user.is_authenticated and request.user.is_staff
    if not authed:
        return HttpResponseForbidden()

    page = {
        'base_url': settings.BASE_URL,
        'favicon': settings.FAVICON,
        'theme': common.get_theme(request),
        'title': _('OAuth - Settings'),
    }
    apis_help = {
        'twitter': 'http://dev.twitter.com/pages/auth',
    }
    v = {}
    id_service = args['id']

    callback_url = request.build_absolute_uri(
        reverse('usettings-oauth', args=[id_service]))

    service = Service.objects.get(id=id_service)
    c = gls_oauth.OAuth1Client(service=service,
                               identifier=request.POST.get('identifier'),
                               secret=request.POST.get('secret'),
                               callback_url=callback_url)

    if c.db.phase == 0 and (not c.request_token_url or
                            not c.authorize_url or
                            not c.access_token_url):
        v['request_token_url'] = request.POST.get('request_token_url', '')
        v['authorize_url'] = request.POST.get('authorize_url', '')
        v['access_token_url'] = request.POST.get('access_token_url', '')
        page['need_custom_urls'] = True

    if 'reset' in request.POST:
        c.reset()
        c.save()
    elif request.method == 'POST':
        if c.db.phase == 0:
            if not c.request_token_url:
                c.set_urls(v['request_token_url'],
                           v['authorize_url'],
                           v['access_token_url'])
            try:
                c.get_request_token()
            except Exception as e:
                page['msg'] = e
            c.save()
        if c.db.phase == 1:
            return HttpResponseRedirect(c.get_authorize_url())

    if request.method == 'GET':
        if c.db.phase == 1:
            if request.GET.get('oauth_token', '') == c.db.token:
                c.consumer.parse_authorization_response(
                    request.get_full_path())
                c.verifier = request.GET.get('oauth_verifier', None)
                c.db.phase = 2

        if c.db.phase == 2:
            try:
                c.get_access_token()
                c.save()
                return HttpResponseRedirect(reverse('usettings-oauth', args=[id_service]))
            except Exception as e:
                page['msg'] = e

    api_help = apis_help.get(service.api,
                             'http://oauth.net/documentation/getting-started/')

    return render(request, 'oauth.html',
                  {'page': page,
                   'is_secure': request.is_secure(),
                   'title': str(service),
                   'api_help': api_help,
                   'callback_url': callback_url,
                   'phase': c.db.phase,
                   'v': v, })


@login_required
def opml(request, **args):
    authed = request.user.is_authenticated and request.user.is_staff
    if not authed:
        return HttpResponseForbidden()

    cmd = args.get('cmd', '')

    if cmd == 'import':
        from xml.dom.minidom import parseString

        if 'opml' in request.FILES:
            xml = request.FILES['opml'].read()

            # Parse OPML
            dom = parseString(xml)
            body = dom.getElementsByTagName('body')
            for e in body[0].childNodes:
                if e.nodeName == 'outline':
                    tp = e.getAttribute('type')
                    if tp == 'rss':
                        xml_url = e.getAttribute('xmlUrl')
                        title = e.getAttribute('text') or \
                            e.getAttribute('title')
                        _import_service(xml_url, title)
                    elif not tp:
                        cls = e.getAttribute('text') or \
                            e.getAttribute('title')
                        cls = cls.lower()
                        for f in e.childNodes:
                            if f.nodeName == 'outline' and \
                                    f.getAttribute('type') == 'rss':
                                xml_url = f.getAttribute('xmlUrl')
                                title = f.getAttribute('text') or \
                                    f.getAttribute('title')
                                _import_service(xml_url, title, cls)

        return HttpResponseRedirect(reverse('usettings-services'))

    elif cmd == 'export':
        excluded_apis = ('selfposts', 'fb')
        services = Service.objects.exclude(api__in=excluded_apis) \
            .order_by('name')

        srvs = []
        for service in services:
            try:
                mod = __import__('glifestream.apis.%s' % service.api,
                                 {}, {}, ['API'])
                mod_api = getattr(mod, 'API')
                service_instance = mod_api(service)
                srvs.extend([{'name': service.name, 'url': u}
                             for u in service_instance.get_urls()])
            except Exception:
                pass

        res = render(request, 'opml.xml', {'services': srvs},
                     content_type='text/xml')
        res['Content-Disposition'] = 'attachment; filename="gls-services.xml"'
        return res

    return HttpResponse()


def _import_service(url, title, cls='webfeed'):
    api_name = 'webfeed'

    if 'flickr.com' in url:
        m = re.search(
            r'flickr.com/services/feeds/photos_public\.gne\?id=([0-9@A-Z]+)', url)
        if m:
            url = m.groups()[0]
        url = url.replace('format=atom', 'format=rss_200')
        api_name = 'flickr'
        cls = 'photos'
    elif 'twitter.com' in url:
        m = re.search(r'twitter.com/1/statuses/user_timeline/(\w+)\.', url)
        if m:
            url = m.groups()[0]
            api_name = 'twitter'
            cls = 'sms'
    elif 'vimeo.com' in url:
        m = re.search(r'vimeo.com/([\w/]+)/\w+/rss', url)
        if m:
            url = m.groups()[0]
            url = url.replace('channels/', 'channel/')
            url = url.replace('groups/', 'group/')
            api_name = 'vimeo'
            cls = 'videos'
    elif 'youtube.com' in url:
        m = re.search(r'gdata.youtube.com/feeds/api/users/(\w+)', url)
        if m:
            url = m.groups()[0]
        api_name = 'youtube'
        cls = 'videos'
    elif 'yelp.com/syndicate' in url:
        api_name = 'yelp'
        cls = 'reviews'

    try:
        try:
            Service.objects.get(api=api_name, url=url)
        except Service.DoesNotExist:
            if api_name in ('vimeo', 'webfeed', 'yelp', 'youtube'):
                display = 'both'
            else:
                display = 'content'
            service = Service(api=api_name, cls=cls, url=url, name=title,
                              display=display)
            service.save()
    except Exception:
        pass

#
# XHR API
#


def api(request, **args):
    authed = request.user.is_authenticated and request.user.is_staff
    if not authed:
        return HttpResponseForbidden()

    cmd = args.get('cmd', '')

    method = request.POST.get('method', 'get')
    id_service = request.POST.get('id', None)

    # Add/edit services
    if cmd == 'service':
        s = {
            'api': request.POST.get('api', ''),
            'name': request.POST.get('name', ''),
            'cls': request.POST.get('cls', ''),
            'url': request.POST.get('url', ''),
            'display': request.POST.get('display', 'content'),
            'public': bool(request.POST.get('public', False)),
            'home': bool(request.POST.get('home', False)),
            'active': bool(request.POST.get('active', False)),
        }
        miss = {}

        # Data validation
        if method == 'post':
            if not s['name']:
                miss['name'] = True
                method = 'get'
            if s['api'] != 'selfposts' and not s['url'] \
               and request.POST.get('timeline', 'user') == 'user':
                miss['url'] = True
                method = 'get'

        # Special cases, predefined
        if s['api'] in ('delicious', 'digg', 'greader', 'lastfm',
                        'stumbleupon', 'yelp'):
            s['display'] = 'both'

        # Save
        if method == 'post':
            try:
                try:
                    if not id_service:
                        raise Service.DoesNotExist
                    srv = Service.objects.get(id=id_service)
                except Service.DoesNotExist:
                    srv = Service()
                for k, v in s.items():
                    setattr(srv, k, v)
            except Exception:
                pass

            try:
                basic_user = request.POST.get('basic_user', None)
                basic_pass = request.POST.get('basic_pass', None)
                access_token = request.POST.get('access_token', None)

                auth = request.POST.get('auth', 'none')
                if auth == 'basic' and basic_user and basic_pass:
                    srv.creds = basic_user + ':' + basic_pass
                elif auth == 'oauth':
                    srv.creds = auth
                elif access_token:
                    srv.creds = access_token
                elif auth == 'none':
                    srv.creds = ''

                s['need_import'] = not srv.id
                srv.save()
                id_service = srv.id
            except Exception:
                pass

        # Get
        if id_service:
            try:
                srv = Service.objects.get(id=id_service)
                if len(miss) == 0:
                    s.update({
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
            s['home'] = True
            s['active'] = True

        if 'creds' not in s:
            s['creds'] = ''

        # Setup fields
        s['fields'] = [
            {'type': 'text', 'name': 'name',
             'value': s['name'], 'label': _('Short name'),
             'miss': miss.get('name', False)},
            {'type': 'text', 'name': 'cls',
             'value': s['cls'], 'label': _('Class name'),
             'hint': _('Any name for the service classification; a category.')}
        ]

        if s['api'] == 'webfeed':
            s['fields'].append({'type': 'text', 'name': 'url',
                                'value': s['url'], 'label': _('URL'),
                                'miss': miss.get('url', False)})

        elif s['api'] in ('fb', 'friendfeed', 'twitter'):
            v = 'user' if s['url'] else 'home'
            s['fields'].append({'type': 'select', 'name': 'timeline',
                                'options': (('user', _('User timeline')),
                                            ('home', _('Home timeline'))),
                                'value': v, 'label': _('Timeline')})
            s['fields'].append({'type': 'text', 'name': 'url',
                                'value': s['url'], 'label': _('ID/Username'),
                                'deps': {'timeline': 'user'}})

        elif s['api'] != 'selfposts':
            s['fields'].append({'type': 'text', 'name': 'url',
                                'value': s['url'], 'label': _('ID/Username'),
                                'miss': miss.get('url', False)})

        if s['api'] in ('webfeed', 'friendfeed', 'twitter'):
            basic_user = ''
            if s['creds'] == 'oauth':
                v = 'oauth'
            elif s['creds']:
                v = 'basic'
                basic_user = s['creds'].split(':', 1)[0]
            else:
                v = 'none'

            s['fields'].append({'type': 'select', 'name': 'auth',
                                'options': (('none', _('none')),
                                            ('basic', _('Basic')),
                                            ('oauth', _('OAuth'))),
                                'value': v, 'label': _('Authorization')})

            if 'id' in s:
                s['fields'].append({'type': 'link', 'name': 'oauth_conf',
                                    'value': _('configure access'),
                                    'href': '#', 'label': '',
                                    'deps': {'auth': 'oauth'}})

            s['fields'].append({'type': 'text', 'name': 'basic_user',
                                'value': basic_user,
                                'label': _('Basic username'),
                                'deps': {'auth': 'basic'}})
            s['fields'].append({'type': 'password', 'name': 'basic_pass',
                                'value': '', 'label': _('Basic password'),
                                'deps': {'auth': 'basic'}})

        if s['api'] in ('webfeed', 'flickr', 'youtube', 'vimeo'):
            s['fields'].append({'type': 'select', 'name': 'display',
                                'options': (('both', _('Title and Contents')),
                                            ('content', _('Contents only')),
                                            ('title', _('Title only'))),
                                'value': s['display'],
                                'label': _("Display entries'")})

        s['fields'].append({'type': 'checkbox', 'name': 'public',
                            'checked': s['public'], 'label': _('Public'),
                            'hint': _('Public services are visible to anyone.')})

        s['fields'].append({'type': 'checkbox', 'name': 'home',
                            'checked': s['home'], 'label': _('Home'),
                            'hint': _('If unchecked, this stream will be still active, but hidden and thus visible '
                                      'only via custom lists.')})

        if s['api'] != 'selfposts':
            s['fields'].append({'type': 'checkbox', 'name': 'active',
                                'checked': s['active'], 'label': _('Active'),
                                'hint': _('If not active, this service will not be further updated.')})

        if 'creds' in s:
            del s['creds']

        s['action'] = request.build_absolute_uri()
        s['save'] = _('Save')
        s['cancel'] = _('Cancel')

        # print(json.dumps(s, indent=2))
        return JsonResponse(s)

    # Import
    elif cmd == 'import' and id_service:
        try:
            service = Service.objects.get(id=id_service)
            mod = __import__('glifestream.apis.%s' %
                             service.api, {}, {}, ['API'])
            mod_api = getattr(mod, 'API')
            service_instance = mod_api(service, False, False)
            service_instance.run()
        except Exception:
            pass

    return HttpResponse()
