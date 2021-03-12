#!/usr/bin/env python
# -*- coding: utf-8 -*-

#  gLifestream Copyright (C) 2009, 2010, 2014, 2015, 2021 Wojciech Polak
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

import datetime
import getopt
import os
import sys
import time
import django
from django.conf import settings
from django.utils.six.moves import range, input

try:
    import workerpool
except ImportError:
    workerpool = None

SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
os.environ['DJANGO_SETTINGS_MODULE'] = 'glifestream.settings'

if hasattr(django, 'setup'):
    django.setup()

from glifestream.stream import media, pshb
from glifestream.stream.models import Service, Entry, Favorite
from glifestream.utils.time import unixnow

if workerpool:
    class WorkerJob(workerpool.Job):

        def __init__(self, fn):
            self.fn = fn

        def run(self):
            self.fn()


def run():
    verbose = 0
    list = False
    force_check = False
    force_overwrite = False
    list_old = False
    delete_old = False
    only_inactive = False
    thumbs = False
    pshb_cmd = False
    fs = {}

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'i:a:lvf',
                                   ['id=',
                                    'api=',
                                    'list',
                                    'verbose',
                                    'force-check',
                                    'force-overwrite',
                                    'delete-old=',
                                    'list-old=',
                                    'only-inactive',
                                    'thumbs-list-orphans',
                                    'thumbs-delete-orphans',
                                    'pshb=',
                                    'email2post',
                                    'init-files-dirs'])
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
                list_old = int(arg)
            elif o == '--delete-old':
                delete_old = int(arg)
            elif o == '--only-inactive':
                only_inactive = True
            elif o == '--thumbs-list-orphans':
                thumbs = 'list-orphans'
            elif o == '--thumbs-delete-orphans':
                thumbs = 'delete-orphans'
            elif o == '--pshb':
                pshb_cmd = arg
            elif o == '--email2post':
                sys.exit(email2post())
            elif o == '--init-files-dirs':
                sys.exit(init_files_dirs())
    except getopt.GetoptError:
        print("Usage: %s [OPTION...]" % sys.argv[0])
        print("""%s -- gLifestream worker

  -a, --api=NAME               API name of services to update
  -i, --id=ID                  ID of the service to update
  -l, --list                   List service IDs
  -f, --force-check            Force service check for updates
      --force-overwrite        Force overwriting unmodified entries
      --list-old=DAYS          List entries older than DAYS
      --delete-old=DAYS        Delete entries older than DAYS
      --only-inactive          Match only inactive entries (hidden)
      --thumbs-list-orphans    List orphaned thumbnails
      --thumbs-delete-orphans  Delete orphaned thumbnails
      --pshb=ACTION            PubSubHubbub's actions: (un)subscribe, list
      --email2post             Post things using e-mail (from stdin)
  """ % sys.argv[0])
        sys.exit(0)

    if list:
        for service in Service.objects.all().order_by('id'):
            print('%4d "%s"  API=%s' % (service.id, service.name, service.api))
        sys.exit(0)

    if pshb_cmd:
        if pshb_cmd == 'subscribe' and 'id' in fs:
            service = Service.objects.get(id=fs['id'])
            r = pshb.subscribe(service, verbose)
            if r['rc'] == 1:
                print('%s: %s' % (sys.argv[0], r['error']))
            elif r['rc'] == 2:
                print('%s: Hub not found.' % sys.argv[0])
            elif r['rc'] == 202:
                print('hub=%s: Accepted for verification.' % r['hub'])
            elif r['rc'] == 204:
                print('hub=%s: Subscription verified.' % r['hub'])
        elif pshb_cmd == 'unsubscribe' and 'id' in fs:
            r = pshb.unsubscribe(fs['id'], verbose)
            if r['rc'] == 1:
                print('%s: No subscription found.' % sys.argv[0])
            elif r['rc'] == 202:
                print('hub=%s: Accepted for verification.' % r['hub'])
            elif r['rc'] == 204:
                print('hub=%s: Unsubscribed.' % r['hub'])
            else:
                print('hub=%s: %s.' % (r['hub'], r['rc']))
        elif pshb_cmd == 'renew':
            pshb.renew_subscriptions(force=force_check, verbose=verbose)
        elif pshb_cmd == 'list':
            pshb.list()
        elif pshb_cmd == 'publish':
            pshb.publish(verbose=verbose)
        else:
            print('%s: Unknown "%s" action.' % (sys.argv[0], pshb_cmd))
            sys.exit(1)
        sys.exit(0)

    if thumbs in ('list-orphans', 'delete-orphans'):
        import re
        ths = {}
        for root, dirs, files in os.walk(os.path.join(settings.MEDIA_ROOT,
                                                      'thumbs')):
            for file in files:
                if file[0] != '.':
                    ths[media.get_thumb_info(file)['rel']] = True
        entries = Entry.objects.all()
        for entry in entries:
            hash = media.get_thumb_hash(entry.link_image)
            t = media.get_thumb_info(hash)['rel'] if hash else ''
            if t in ths:
                del ths[t]
            for hash in re.findall('\[GLS-THUMBS\]/([a-f0-9]{40})',
                                   entry.content):
                t = media.get_thumb_info(hash)['rel']
                if t in ths:
                    del ths[t]
        if thumbs == 'delete-orphans':
            if verbose:
                print('Files to remove: %d' % len(ths))
            for file in ths:
                file = os.path.join(settings.MEDIA_ROOT, file)
                os.remove(file)
        else:
            for file in ths:
                print(file)
        sys.exit(0)

    if list_old or delete_old:
        days = list_old if list_old else delete_old
        n = time.mktime(unixnow()) - (86400 * days)
        rt = datetime.datetime.fromtimestamp(n).date()
        if 'id' in fs:
            lst = fs['id'].split(',')
            if len(lst) > 1:
                fs['service__id__in'] = lst
            else:
                fs['service__id'] = int(fs['id'])
            del fs['id']
        elif 'api' in fs:
            lst = fs['api'].split(',')
            if len(lst) > 1:
                fs['service__api__in'] = lst
            else:
                fs['service__api'] = fs['api']
            del fs['api']
        fs['service__public'] = False
        fs['protected'] = False
        fs['date_published__lte'] = rt
        fs['date_inserted__lte'] = rt
        if only_inactive:
            fs['active'] = False
        favs = Favorite.objects.all().values('entry')
        if list_old:
            for entry in Entry.objects.filter(**fs).exclude(id__in=favs):
                print('%4d "%s" by %s' % (entry.id,
                                          entry.title,
                                          entry.author_name))
        elif delete_old:
            Entry.objects.filter(**fs).exclude(id__in=favs).delete()
        sys.exit(0)
    else:
        if not force_check or 'id' not in fs:
            fs['active'] = True

    if force_overwrite:
        sel = input(
            "WARNING: This may create thumbnail orphans! Continue Y/N? ").strip()
        if sel != 'Y':
            sys.exit(0)

    try:
        last1 = Entry.objects.filter(service__public=True).\
            order_by('-date_published')[0]
    except IndexError:
        last1 = None

    if workerpool:
        pool = workerpool.WorkerPool(size=10)
    else:
        pool = None

    for service in Service.objects.filter(**fs):
        try:
            mod = __import__('glifestream.apis.%s' % service.api,
                             {}, {}, ['API'])
        except ImportError:
            continue
        mod_api = getattr(mod, 'API')

        if service.last_checked and hasattr(mod_api, 'limit_sec'):
            if not force_check:
                d = datetime.datetime.now() - service.last_checked
                if d.seconds < mod_api.limit_sec:
                    continue

        api = mod_api(service, verbose, force_overwrite)
        if pool:
            pool.put(WorkerJob(api.run))
        else:
            api.run()

    if pool:
        pool.shutdown()
        pool.wait()

    try:
        last2 = Entry.objects.filter(service__public=True).\
            order_by('-date_published')[0]
    except IndexError:
        last2 = None

    if last2 and last1 != last2:
        pshb.publish(verbose=verbose)


def email2post():
    from glifestream.apis import mail
    api = mail.API()
    return api.share(sys.stdin)


def init_files_dirs():
    """Create initial directories and files."""

    upload = os.path.join(settings.MEDIA_ROOT, 'upload')
    _create_dir(upload)

    thumbs = os.path.join(settings.MEDIA_ROOT, 'thumbs')
    _create_dir(thumbs)

    for i in range(0, 10):
        _create_dir(os.path.join(thumbs, str(i)))
    for i in 'abcdef':
        _create_dir(os.path.join(thumbs, i))

    print("""
Make sure that 'static/thumbs/*' and 'static/upload' directories exist
and all have write permissions by your webserver.
""")

    template_dir = settings.TEMPLATES[0]['DIRS'][0]
    template_files = (
        'user-about.html',
        'user-copyright.html',
        'user-scripts.js',
    )
    try:
        for i in template_files:
            file = os.path.join(template_dir, i)
            if not os.path.isfile(file):
                print("Creating empty file '%s'" % file)
                open(file, 'w').close()
    except Exception as exc:
        print(exc)
        return 1

    return 0


def _create_dir(d, verbose=True):
    if not os.path.isdir(d):
        if verbose:
            print("Creating directory '%s'" % d)
        os.mkdir(d)


if __name__ == '__main__':
    run()
