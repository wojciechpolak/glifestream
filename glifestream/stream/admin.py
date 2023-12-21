"""
#  gLifestream Copyright (C) 2009, 2010, 2014, 2023 Wojciech Polak
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

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _
from glifestream.stream.models import Service, Entry, Media, Favorite, List


def deactivate(modeladmin, request, queryset):
    queryset.update(active=False)


deactivate.short_description = _("Deactivate item")


def activate(modeladmin, request, queryset):
    queryset.update(active=True)


activate.short_description = _("Activate item")


def truncate_title(self):
    if self.title:
        return self.title[0:70]
    return '---'


class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'api', 'url', 'last_modified', 'public',
                    'active', 'home')
    fieldsets = (
        (None, {'fields': ('api', 'name', 'url', 'creds', 'display', 'public',
                           'active', 'home')}),
        (_('Additional, optional fields'),
         {'classes': ('collapse',), 'fields': ('link', 'cls'),
          }),
        (_('Fields updated automatically by gLifestream'),
         {'classes': ('collapse',),
          'fields': ('etag', 'last_modified', 'last_checked'),
          })
    )
    search_fields = ['url', 'name']
    actions = [deactivate, activate]


class EntryAdmin(admin.ModelAdmin):
    list_display = (truncate_title, 'service', 'active', 'view_website_link')
    list_filter = ('active', 'service',)
    search_fields = ['id', 'title', 'content']
    actions = [deactivate, activate]

    def view_website_link(self, obj):
        website_url = reverse('entry', args=[obj.id])
        return format_html('<a href="{}" target="_blank">View</a>',
                           website_url)

    view_website_link.short_description = 'Link'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['website_link'] = self.view_website_link(
            Entry.objects.get(pk=object_id))
        return super().change_view(request, object_id,
                                   form_url, extra_context)


class MediaAdmin(admin.ModelAdmin):
    list_display = ('entry', 'file',)
    raw_id_fields = ('entry',)


class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'entry',)
    list_filter = ('user',)
    raw_id_fields = ('entry',)


class ListAdmin(admin.ModelAdmin):
    list_display = ('user', 'name',)
    list_filter = ('user',)


admin.site.register(Service, ServiceAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(Media, MediaAdmin)
admin.site.register(Favorite, FavoriteAdmin)
admin.site.register(List, ListAdmin)
