#  gLifestream Copyright (C) 2009, 2010, 2012, 2014, 2015 Wojciech Polak
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
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.contrib.sites.requests import RequestSite
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from glifestream.gauth import gls_openid
from glifestream.gauth.forms import OpenIdForm, AuthenticationRememberMeForm
from glifestream.gauth.models import OpenId
from glifestream.utils import common

try:
    import facebook
    if not hasattr(facebook, 'GraphAPI'):
        facebook = None
except ImportError:
    facebook = None


@never_cache
def login(request, template_name='login.html',
          redirect_field_name=REDIRECT_FIELD_NAME):

    redirect_to = request.GET.get(redirect_field_name, urlresolvers.reverse('index'))

    if request.method == 'POST':
        form = AuthenticationRememberMeForm(data=request.POST,)
        if form.is_valid():
            if not redirect_to or '//' in redirect_to or ' ' in redirect_to:
                redirect_to = settings.BASE_URL + '/'

            if not form.cleaned_data['remember_me']:
                request.session.set_expiry(0)

            from django.contrib.auth import login
            login(request, form.get_user())

            if request.session.test_cookie_worked():
                request.session.delete_test_cookie()

            return HttpResponseRedirect(redirect_to)
    else:
        form = AuthenticationRememberMeForm(request,)

    request.session.set_test_cookie()

    if Site._meta.installed:
        current_site = Site.objects.get_current()
    else:
        current_site = RequestSite(request)

    page = {
        'robots': 'noindex,nofollow',
        'favicon': settings.FAVICON,
        'theme': common.get_theme(request),
    }

    return render(request, template_name,
                  {'page': page,
                   'form': form,
                   'site': current_site,
                   'site_name': current_site.name,
                   'is_secure': request.is_secure(),
                   redirect_field_name: redirect_to})


@never_cache
def login_friend(request, template_name='registration/login.html',
                 redirect_field_name=REDIRECT_FIELD_NAME):

    redirect_to = request.GET.get(redirect_field_name, urlresolvers.reverse('index'))
    if not redirect_to or '//' in redirect_to or ' ' in redirect_to:
        redirect_to = settings.BASE_URL + '/'

    if not facebook or settings.FACEBOOK_APP_ID == '':
        return HttpResponseRedirect(redirect_to)

    are_friends = False
    try:
        fb_user = facebook.get_user_from_cookie(request.COOKIES,
                                                settings.FACEBOOK_APP_ID,
                                                settings.FACEBOOK_APP_SECRET)
        if fb_user and 'uid' in fb_user:
            if settings.FACEBOOK_USER_ID != fb_user['uid']:
                graph = facebook.GraphAPI(fb_user['access_token'])
                friends = graph.get_connections('me', 'friends')
                are_friends = settings.FACEBOOK_USER_ID in \
                    [friend['id'] for friend in friends['data']]
                if are_friends:
                    profile = graph.get_object('me')
                    request.session['fb_username'] = profile['first_name']
                    request.session['fb_profile_url'] = profile['link']
            else:
                are_friends = True
    except Exception as e:
        raise e

    if not are_friends:
        return HttpResponseRedirect(redirect_to)

    from django.contrib.auth import login

    user = User.objects.get(username='friend')
    if user is not None:
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        if user.is_active:
            login(request, user)
            return HttpResponseRedirect(redirect_to)

    return HttpResponseRedirect(redirect_to)


@never_cache
def xrds(request, **args):
    xrds_tpl = """<?xml version="1.0" encoding="UTF-8"?>
<xrds:XRDS
    xmlns:xrds="xri://$xrds"
    xmlns:openid="http://openid.net/xmlns/1.0"
    xmlns="xri://$xrd*($v*2.0)">
  <XRD>
    <Service priority="1">
      <Type>http://specs.openid.net/auth/2.0/return_to</Type>
      <URI priority="1">%s</URI>
      <URI priority="2">%s</URI>
    </Service>
  </XRD>
</xrds:XRDS>
"""
    body = xrds_tpl % (request.build_absolute_uri('openid'),
                       request.build_absolute_uri(
                           urlresolvers.reverse('usettings-openid')))
    res = HttpResponse(body, content_type='application/xrds+xml')
    res['X-Robots-Tag'] = 'noindex'
    return res


@never_cache
def openid(request, template_name='openid.html',
           redirect_field_name=REDIRECT_FIELD_NAME):
    msg = None
    redirect_to = urlresolvers.reverse('index')
    if not redirect_to or '//' in redirect_to or ' ' in redirect_to:
        redirect_to = settings.BASE_URL + '/'

    if not gls_openid.openid:
        return HttpResponseRedirect(redirect_to)

    if request.method == 'POST':
        form = OpenIdForm(data=request.POST,)
        if form.is_valid():
            if not form.cleaned_data['remember_me']:
                request.session.set_expiry(0)

            rs = gls_openid.start(request,
                                  form.cleaned_data['openid_identifier'])
            if 'res' in rs:
                return rs['res']
            elif 'msg' in rs:
                msg = rs['msg']
        else:
            msg = _('Invalid OpenID identifier')

    elif request.method == 'GET':

        if request.GET.get('openid.mode', None):
            rs = gls_openid.finish(request)
            if 'msg' in rs:
                msg = rs['msg']
            elif 'identity_url' in rs:
                try:
                    db = OpenId.objects.get(identity=rs['identity_url'])
                    if db:
                        user = db.user
                        user.backend = 'django.contrib.auth.backends.ModelBackend'
                        if user.is_active:
                            from django.contrib.auth import login
                            login(request, user)

                            if request.session.test_cookie_worked():
                                request.session.delete_test_cookie()
                            return HttpResponseRedirect(redirect_to)
                except OpenId.DoesNotExist:
                    pass
                msg = _('OpenID account match error')

    form = OpenIdForm(request,)
    request.session.set_test_cookie()

    if Site._meta.installed:
        current_site = Site.objects.get_current()
    else:
        current_site = RequestSite(request)

    page = {
        'robots': 'noindex,nofollow',
        'favicon': settings.FAVICON,
        'theme': common.get_theme(request),
        'msg': msg,
    }

    return render(request, template_name,
                  {'page': page,
                   'form': form,
                   'site': current_site,
                   'site_name': current_site.name,
                   'is_secure': request.is_secure(),
                   redirect_field_name: redirect_to})
