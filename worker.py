#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

import os
import sys
import time
import datetime
import getopt
import settings

try:
    import workerpool
except ImportError:
    workerpool = None

SITE_ROOT = os.path.dirname (os.path.realpath (__file__))
os.environ['DJANGO_SETTINGS_MODULE'] = 'glifestream.settings'
sys.path.insert (0, os.path.join (SITE_ROOT, '../'))

from django.core.management import setup_environ
setup_environ (settings)
from django.conf import settings
from glifestream.utils.time import unixnow
from glifestream.stream.models import Service, Entry, Favorite
from glifestream.stream import media

if workerpool:
    class WorkerJob (workerpool.Job):
        def __init__ (self, fn):
            self.fn = fn
        def run (self):
            self.fn ()

def run ():
    verbose = 0
    list = False
    force_check = False
    force_overwrite = False
    list_old = False
    delete_old = False
    thumbs = False
    fs = {}

    try:
        opts, args = getopt.getopt (sys.argv[1:], 'i:a:lvf',
                                    ['id=',
                                     'api=',
                                     'list',
                                     'verbose',
                                     'force-check',
                                     'force-overwrite',
                                     'delete-old=',
                                     'list-old=',
                                     'thumbs-list-orphans',
                                     'thumbs-delete-orphans'])
        for o, arg in opts:
            if o in ('-a', '--api'):
                fs['api'] = arg
            elif o in ('-i', '--id'):
                fs['id'] = arg
            elif o in ('-l', '--list'):
                list = True
            elif o in ('-v', '--verbose'):
                verbose += 1
            elif o in ('-f', '--force-check'):
                force_check = True
            elif o == '--force-overwrite':
                force_overwrite = True
            elif o == '--list-old':
                list_old = int (arg)
            elif o == '--delete-old':
                delete_old = int (arg)
            elif o == '--thumbs-list-orphans':
                thumbs = 'list-orphans'
            elif o == '--thumbs-delete-orphans':
                thumbs = 'delete-orphans'
    except getopt.GetoptError:
        print "Usage: %s [OPTION...]" % sys.argv[0]
        print """%s -- gLifestream worker

  -a, --api=NAME               API name of services to update
  -i, --id=ID                  ID of the service to update
  -l, --list                   List service IDs
  -f, --force-check            Force service check for updates
      --force-overwrite        Force overwriting unmodified entries
      --list-old=DAYS          List entries older than DAYS
      --delete-old=DAYS        Delete entries older than DAYS
      --thumbs-list-orphans    List orphaned thumbnails
      --thumbs-delete-orphans  Delete orphaned thumbnails
  """ % sys.argv[0]
        sys.exit (0)

    if list:
        for service in Service.objects.all ().order_by ('id'):
            print '%4d "%s"  API=%s' % (service.id, service.name, service.api)
        sys.exit (0)

    if thumbs in ('list-orphans', 'delete-orphans'):
        import re
        ths = {}
        for root, dirs, files in os.walk (os.path.join (settings.MEDIA_ROOT,
                                                        'thumbs')):
            for file in files:
                if file[0] != '.':
                    ths[media.get_thumb_info (file)['rel']] = True
        entries = Entry.objects.all ()
        for entry in entries:
            hash = media.get_thumb_hash (entry.link_image)
            t = media.get_thumb_info (hash)['rel'] if hash else ''
            if t in ths: del ths[t]
            for hash in re.findall ('\[GLS-THUMBS\]/([a-f0-9]{40})',
                                    entry.content):
                t = media.get_thumb_info (hash)['rel']
                if t in ths: del ths[t]
        if thumbs == 'delete-orphans':
            if verbose:
                print 'Files to remove: %d' % len (ths)
            for file in ths:
                file = os.path.join (settings.MEDIA_ROOT, file)
                os.remove (file)
        else:
            for file in ths:
                print file
        sys.exit (0)

    if list_old or delete_old:
        days = list_old if list_old else delete_old
        n = time.mktime (unixnow ()) - (86400 * days)
        rt = datetime.datetime.fromtimestamp (n).date ()
        if 'id' in fs:
            lst = fs['id'].split (',')
            if len (lst) > 1:
                fs['service__id__in'] = lst
            else:
                fs['service__id'] = int (fs['id'])
            del fs['id']
        elif 'api' in fs:
            lst = fs['api'].split (',')
            if len (lst) > 1:
                fs['service__api__in'] = lst
            else:
                fs['service__api'] = fs['api']
            del fs['api']
        fs['service__public'] = False
        fs['protected'] = False
        fs['date_published__lte'] = rt
        fs['date_inserted__lte'] = rt
        favs = Favorite.objects.all ().values ('entry')
        if list_old:
            for entry in Entry.objects.filter (**fs).exclude (id__in=favs):
                print '%4d "%s" by %s' % (entry.id,
                                          entry.title,
                                          entry.author_name)
        elif delete_old:
            Entry.objects.filter (**fs).exclude (id__in=favs).delete ()
        sys.exit (0)
    else:
        fs['active'] = True

    if force_overwrite:
        sel = raw_input ("WARNING: This may create thumbnail orphans! Continue Y/N? ").strip ()
        if sel != 'Y':
            sys.exit (0)

    if workerpool:
        pool = workerpool.WorkerPool (size=10)
    else:
        pool = None

    for service in Service.objects.filter (**fs):
        try:
            mod = __import__ ('apis.%s' % service.api, {}, {}, ['API'])
        except ImportError:
            continue
        mod_api = getattr (mod, 'API')

        if service.last_checked and hasattr (mod_api, 'limit_sec'):
            if not force_check:
                d = datetime.datetime.now () - service.last_checked
                if d.seconds < mod_api.limit_sec:
                    continue

        api = mod_api (service, verbose, force_overwrite)
        if pool:
            pool.put (WorkerJob (api.run))
        else:
            api.run ()

    if pool:
        pool.shutdown ()
        pool.wait ()

if __name__ == '__main__':
    run ()
