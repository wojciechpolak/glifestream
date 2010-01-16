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

from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _
from glifestream.utils.time import now

try:
    from djangosphinx.models import SphinxSearch
except ImportError:
    class SphinxSearch:
        query = None
        def __init__ (self, **va):
            pass

class Service (models.Model):
    API_CHOICES = (
        ('webfeed',     'Webfeed'),
        ('selfposts',   'Self Posts'),
        ('twitter',     'Twitter'),
        ('friendfeed',  'FriendFeed'),
        ('youtube',     'YouTube'),
        ('vimeo',       'Vimeo'),
        ('delicious',   'Delicious'),
        ('digg',        'Digg'),
        ('greader',     'Google Reader'),
        ('flickr',      'Flickr'),
        ('picasaweb',   'Picasa Web'),
        ('lastfm',      'Last.fm'),
        ('stumbleupon', 'StumbleUpon'),
        ('yelp',        'Yelp'),
        ('identica',    'Identi.ca'),
    )
    api = models.CharField (_('API'), max_length=16, choices=API_CHOICES,
                            default='feed', db_index=True)
    cls = models.CharField (_('Custom CSS Class'), max_length=16, null=True,
                            blank=True)
    url = models.CharField (_('URL or Username'), max_length=255, blank=True)
    creds = models.CharField (_('Credentials'), max_length=128, null=True,
                              blank=True)
    name = models.CharField (_('Short name'), max_length=48)
    link = models.URLField (_('WWW Link'), verify_exists=False, blank=True)
    etag = models.CharField ('ETag', max_length=64, blank=True)
    last_modified = models.DateTimeField (_('Last modified'), null=True,
                                          blank=True)
    last_checked = models.DateTimeField (_('Last checked'), null=True,
                                         blank=True)
    DISPLAY_CHOICES = (
        ('both', _('Title and Contents')),
        ('content', _('Contents only')),
        ('title', _('Title only')),
    )
    display = models.CharField (_("Display entries'"), max_length=8,
                                choices=DISPLAY_CHOICES, default='both',
                                null=False, blank=False)
    public = models.BooleanField (_('Public'), default=False, db_index=True,
        help_text=_('Public services are visible to anyone.'))
    active = models.BooleanField (_('Active'), default=True,
        help_text=_('If not active, this service will not be further updated.'))
    home = models.BooleanField (_('Home visible'), default=True,
        help_text=_('If unchecked, this stream will be still active, but hidden and thus visible only via custom lists.'))

    class Meta:
        verbose_name = _('Service')
        verbose_name_plural = _('Services')
        ordering = ('-public', 'name', 'url',)

    def save (self):
        if not self.cls:
            self.cls = self.api
        super (Service, self).save ()

    def __unicode__ (self):
        return u'%s' % self.name


class Entry (models.Model):
    service = models.ForeignKey (Service, verbose_name=_('Service'),
                                 null=False, blank=False)
    title = models.CharField (_('Title'), max_length=255)
    link = models.URLField (_('Link'),)
    link_image = models.CharField (_('Image Link'), max_length=255, blank=True)
    content = models.TextField (_('Contents'), blank=True)
    date_published = models.DateTimeField (_('Date published'), null=True,
                                           blank=True, db_index=True)
    date_updated = models.DateTimeField (_('Date updated'), null=True,
                                         blank=True)
    date_inserted = models.DateTimeField ('Date inserted', null=False,
                                         blank=True, editable=False)
    guid = models.CharField ('GUID', max_length=200)
    author_name = models.CharField (_("Author's Name"), max_length=64,
                                    blank=True)
    author_email = models.EmailField (_("Author's Email"), blank=True)
    author_uri = models.CharField (_("Author's URI"), max_length=128,
                                   blank=True)
    geolat = models.DecimalField (_('Geo Latitude'), max_digits=13,
                                  decimal_places=10, blank=True, null=True)
    geolng = models.DecimalField (_('Geo Longitude'), max_digits=13,
                                  decimal_places=10, blank=True, null=True)
    idata = models.CharField ('Internal data', max_length=64,
                              blank=True, editable=False)
    protected = models.BooleanField (_('Protected'), default=False,
        help_text=_('Protect from possible overwriting by next update.'))
    active = models.BooleanField (_('Active'), default=True,
        help_text=_('If not active, this entry will not be shown.'))

    sphinx = SphinxSearch (index=getattr (settings, 'SPHINX_INDEX_NAME',
                                          'glifestream'))

    class Meta:
        verbose_name = _('Entry')
        verbose_name_plural = _('Entries')
        ordering = '-date_published',
        unique_together = (('service', 'guid'),)

    def save (self):
        if not self.date_inserted:
            self.date_inserted = now ()
        super (Entry, self).save ()

    def __unicode__ (self):
        return u'%s: %s' % (self.service.name, self.title[0:60])


class Media (models.Model):
    entry = models.ForeignKey (Entry, verbose_name=_('Entry'),
                               null=False, blank=False)
    file = models.FileField (upload_to='upload/%Y/%m/%d')

    class Meta:
        verbose_name = _('Media')
        verbose_name_plural = _('Media')
        unique_together = (('entry', 'file'),)

    def __unicode__ (self):
        return u'%s: %s' % (self.entry.title, self.file.name)


class Favorite (models.Model):
    user = models.ForeignKey (User, db_index=True)
    entry = models.ForeignKey (Entry, verbose_name=_('Entry'),
                               null=False, blank=False)
    date_added = models.DateTimeField (auto_now_add=True)

    class Meta:
        verbose_name = _('Favorite')
        verbose_name_plural = _('Favorites')
        ordering = '-date_added',
        unique_together = (('user', 'entry'),)

    def __unicode__ (self):
        return u'%s: %s' % (self.user, self.entry.title[0:60])


class List (models.Model):
    user = models.ForeignKey (User, db_index=True)
    name = models.CharField (_('Name'), max_length=48, null=False, blank=False)
    slug = models.CharField (_('Slug'), max_length=48, null=False, blank=True,
                             editable=False)
    services = models.ManyToManyField (Service)

    class Meta:
        verbose_name = _('List')
        verbose_name_plural = _('Lists')
        ordering = 'name',
        unique_together = (('user', 'slug'),)

    def save (self):
        self.slug = slugify (self.name)
        super (List, self).save ()

    def __unicode__ (self):
        return u'%s: %s' % (self.user, self.name)
