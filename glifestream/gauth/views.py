"""
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
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from django.conf import settings
from django.urls import reverse
from django.contrib.auth import login as django_login
from django.contrib.auth import update_session_auth_hash, REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import login_required
from django.contrib.sites.requests import RequestSite
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from glifestream.gauth.forms import AuthenticationRememberMeForm
from glifestream.utils import common


@never_cache
def login(request, template_name='login.html', redirect_field_name=REDIRECT_FIELD_NAME):

    redirect_to = request.GET.get(redirect_field_name, reverse('index'))

    if request.method == 'POST':
        form = AuthenticationRememberMeForm(
            data=request.POST,
        )
        if form.is_valid():
            if not redirect_to or '//' in redirect_to or ' ' in redirect_to:
                redirect_to = settings.BASE_URL + '/'

            if not form.cleaned_data['remember_me']:
                request.session.set_expiry(0)

            django_login(request, form.get_user())

            if request.session.test_cookie_worked():
                request.session.delete_test_cookie()

            return HttpResponseRedirect(redirect_to)
    else:
        form = AuthenticationRememberMeForm(
            request,
        )

    request.session.set_test_cookie()

    current_site = RequestSite(request)

    page = {
        'robots': 'noindex,nofollow',
        'favicon': settings.FAVICON,
        'pwa': getattr(settings, 'PWA_APP_NAME', None),
        'theme': common.get_theme(request),
    }

    return render(
        request,
        template_name,
        {
            'page': page,
            'form': form,
            'site': current_site,
            'site_name': current_site.name,
            'is_secure': request.is_secure(),
            redirect_field_name: redirect_to,
        },
    )


@login_required
@never_cache
def change_password(request):
    # Only allow access when forced password change is required.
    must_change = getattr(
        getattr(request.user, 'userprofile', None), 'must_change_password', False
    )
    if not must_change:
        return HttpResponseForbidden()

    page = {
        'robots': 'noindex,nofollow',
        'favicon': settings.FAVICON,
        'pwa': getattr(settings, 'PWA_APP_NAME', None),
        'theme': common.get_theme(request),
    }

    if request.method == 'POST':
        password1 = request.POST.get('new_password1', '')
        password2 = request.POST.get('new_password2', '')

        if not password1 or not password2:
            return render(
                request,
                'change_password.html',
                {'page': page, 'error': _('Please fill in both password fields.')},
            )

        if password1 != password2:
            return render(
                request,
                'change_password.html',
                {'page': page, 'error': _('Passwords do not match.')},
            )

        request.user.set_password(password1)
        request.user.save()

        # Clear the forced password change flag.
        try:
            profile = request.user.userprofile
            profile.must_change_password = False
            profile.save()
        except AttributeError:
            pass

        # Keep the user logged in after password change.
        update_session_auth_hash(request, request.user)

        return HttpResponseRedirect(reverse('index'))

    return render(request, 'change_password.html', {'page': page})
