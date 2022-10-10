#  gLifestream Copyright (C) 2009, 2010, 2013, 2014, 2015 Wojciech Polak
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
from django.urls import path
from django.conf.urls import url, include
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.views.static import serve as static_serve
from glifestream.gauth.views import login
from glifestream.stream import views as sv


admin.autodiscover()

handler404 = 'glifestream.stream.views.page_not_found'
handler500 = 'glifestream.stream.views.page_internal_error'

urlpatterns = [
    url(r'^$', sv.index, name='index'),
    url(r'^(?P<year>\d{4})/$', sv.index),
    url(r'^(?P<year>\d{4})/(?P<month>\d{2})/$', sv.index),
    url(r'^(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$', sv.index),

    url(r'^public/$', sv.index, {'ctx': 'public'}, name='public'),
    url(r'^public/(?P<year>\d{4})/$', sv.index, {
        'ctx': 'public'}),
    url(r'^public/(?P<year>\d{4})/(?P<month>\d{2})/$', sv.index,
        {'ctx': 'public'}),
    url(r'^public/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$', sv.index,
        {'ctx': 'public'}),

    url(r'^entry/(?P<entry>\d+)(/.*)?$', sv.index, {}, name='entry'),
    url(r'^api/(?P<cmd>[a-z]+)$', sv.api, name='api'),

    url(r'^favorites/$', sv.index, {
        'ctx': 'favorites'}, name='favorites'),
    url(r'^favorites/(?P<year>\d{4})/$', sv.index, {
        'ctx': 'favorites'}),
    url(r'^favorites/(?P<year>\d{4})/(?P<month>\d{2})/$',
        sv.index, {'ctx': 'favorites'}),
    url(r'^favorites/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$',
        sv.index, {'ctx': 'favorites'}),

    url(r'^list/(?P<list>[a-z0-9\-]+)/$', sv.index, {}, name='list'),
    url(r'^list/(?P<list>[a-z0-9\-]+)/(?P<year>\d{4})/$', sv.index),
    url(r'^list/(?P<list>[a-z0-9\-]+)/(?P<year>\d{4})/(?P<month>\d{2})/$',
        sv.index),
    url(r'^list/(?P<list>[a-z0-9\-]+)/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/$',
        sv.index),

    url(r'^pshb/(?P<id>[a-f0-9]{20})$',
        sv.pshb_dispatcher, {}, name='pshb'),

    url(r'^login/?$', login, name='login'),
    url(r'^logout/?$', LogoutView.as_view(next_page='./'), name='logout'),

    url(r'^bookmarklet/', include(
        'glifestream.bookmarklet.urls')),
    url(r'^settings/', include('glifestream.usettings.urls')),

    path('admin/', admin.site.urls),
]

urlpatterns += [
    url(r'^media/(?P<path>.*)$', static_serve,
        {'document_root': settings.MEDIA_ROOT})
]
