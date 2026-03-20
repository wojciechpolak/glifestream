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

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Redirect users with must_change_password=True to the change-password page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            # Only check if user has a profile with must_change_password
            try:
                profile = getattr(request.user, 'userprofile', None)
                if profile and profile.must_change_password:
                    change_password_url = reverse('change-password')
                    exempt_paths = (
                        change_password_url,
                        reverse('logout'),
                        '/static/',
                        '/media/',
                        '/admin/',
                    )
                    if not any(request.path.startswith(p) for p in exempt_paths):
                        return HttpResponseRedirect(change_password_url)
            except AttributeError:
                pass

        response: HttpResponse = self.get_response(request)
        return response
