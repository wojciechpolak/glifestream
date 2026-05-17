"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
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

from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from glifestream.stream.models import List
from glifestream.usettings.common import (
    build_settings_page,
    get_staff_settings_user,
)
from glifestream.usettings.forms import ListForm


@login_required
def lists(request: HttpRequest, **args: Any) -> HttpResponse:
    user = get_staff_settings_user(request)
    if isinstance(user, HttpResponseForbidden):
        return user

    page = build_settings_page(request, title=_('Lists - Settings'), menu='lists')
    curlist = ''
    lists_user = List.objects.filter(user=user).order_by('name')

    if 'list' in args:
        try:
            list_user = List.objects.get(user=user, slug=args['list'])
            curlist = args['list']
        except List.DoesNotExist:
            list_user = List(user=user)
    else:
        list_user = List(user=user)

    if request.method == 'POST':
        if request.POST.get('delete', False):
            list_user.delete()
            return HttpResponseRedirect(reverse('usettings-lists'))
        form = ListForm(request.POST, instance=list_user)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse('usettings-lists-slug', args=[list_user.slug])
            )
    else:
        form = ListForm(instance=list_user)

    return render(
        request,
        'lists.html',
        {
            'page': page,
            'authed': True,
            'is_secure': request.is_secure(),
            'user': request.user,
            'lists': lists_user,
            'curlist': curlist,
            'form': form,
        },
    )
