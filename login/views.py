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

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.models import User
from django.views.decorators.cache import never_cache
from django.conf import settings
from django.core import urlresolvers
from django.contrib.sites.models import RequestSite, Site
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from glifestream.login.forms import AuthenticationRememberMeForm

try:
    import facebook
except ImportError:
    facebook = None

@never_cache
def login (request, template_name='registration/login.html',
           redirect_field_name=REDIRECT_FIELD_NAME):

    redirect_to = request.REQUEST.get (redirect_field_name,
                                       urlresolvers.reverse ('index'))

    if request.method == 'POST':
        form = AuthenticationRememberMeForm (data = request.POST,)
        if form.is_valid ():
            if not redirect_to or '//' in redirect_to or ' ' in redirect_to:
                redirect_to = settings.BASE_URL + '/'

            if not form.cleaned_data ['remember_me']:
                request.session.set_expiry (0)

            from django.contrib.auth import login
            
            login (request, form.get_user ())
            
            if request.session.test_cookie_worked ():
                request.session.delete_test_cookie ()
                
            return HttpResponseRedirect (redirect_to)
    else:
        form = AuthenticationRememberMeForm (request,)

    request.session.set_test_cookie ()

    if Site._meta.installed:
        current_site = Site.objects.get_current ()
    else:
        current_site = RequestSite (request)

    gl_theme = request.COOKIES.get ('glifestream_theme', settings.THEMES[0])
    if not gl_theme in settings.THEMES:
        gl_theme = settings.THEMES[0]
    page = {
        'robots': 'noindex,nofollow',
        'theme': gl_theme,
    }

    return render_to_response (template_name,
                               { 'page': page,
                                 'form': form,
                                 'site': current_site,
                                 'site_name': current_site.name,
                                 redirect_field_name: redirect_to },
                               context_instance = RequestContext (request))

@never_cache
def login_friend (request, template_name='registration/login.html',
                  redirect_field_name=REDIRECT_FIELD_NAME):

    redirect_to = request.REQUEST.get (redirect_field_name,
                                       urlresolvers.reverse ('index'))
    if not redirect_to or '//' in redirect_to or ' ' in redirect_to:
        redirect_to = settings.BASE_URL + '/'

    if not facebook or settings.FACEBOOK_API_KEY == '':
        return HttpResponseRedirect (redirect_to)

    are_friends = False
    try:
        fb = facebook.Facebook (settings.FACEBOOK_API_KEY,
                                settings.FACEBOOK_SECRET_KEY)
        if fb.check_session (request):
            user_id = fb.users.getLoggedInUser ()
            if settings.FACEBOOK_USER_ID != user_id:
                are_friends = fb.friends.areFriends ([settings.FACEBOOK_USER_ID],
                                                     [user_id])
                if are_friends:
                    data = fb.users.getInfo ([user_id], ['first_name',
                                                         'profile_url'])
                    request.session['fb_username'] = data[0]['first_name']
                    request.session['fb_profile_url'] = data[0]['profile_url']
            else:
                are_friends = True
    except Exception, e:
        raise e

    if not are_friends:
        return HttpResponseRedirect (redirect_to)

    from django.contrib.auth import login

    user = User.objects.get (username='friend')
    if user is not None:
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        if user.is_active:
            login (request, user)
            return HttpResponseRedirect (redirect_to)

    return HttpResponseRedirect (redirect_to)
