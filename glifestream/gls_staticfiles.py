"""
#  gLifestream Copyright (C) 2023 Wojciech Polak
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

from glob import has_magic
from typing import Any

from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.apps import StaticFilesConfig
from django.core.checks import CheckMessage, Error, Tags, register


class GlsStaticFilesConfig(StaticFilesConfig):
    ignore_patterns = [
        '.*',
        '*~',
        '*.scss',
    ]

    def ready(self) -> None:
        super().ready()
        register(check_pipeline_sources, Tags.staticfiles)


def check_pipeline_sources(
    app_configs: Any = None, **kwargs: Any
) -> list[CheckMessage]:
    """Every file a django-pipeline bundle is made of must exist.

    Pipeline leaves a missing file out of its bundle without a word, so
    collectstatic would publish a js/main.js without the page script. The
    check is tagged `staticfiles`, the one tag collectstatic runs.
    """
    pipeline: dict[str, Any] = settings.PIPELINE
    errors: list[CheckMessage] = []
    for kind in ('JAVASCRIPT', 'STYLESHEETS'):
        bundles: dict[str, dict[str, Any]] = pipeline.get(kind, {})
        for name, bundle in bundles.items():
            for path in bundle['source_filenames']:
                if has_magic(path) or finders.find(path):
                    continue
                errors.append(
                    Error(
                        f'The pipeline bundle {name!r} lists {path}, which no '
                        'static files finder can find.',
                        hint='Build it with `npm ci && npm run build`.'
                        if path.startswith('js/dist/')
                        else None,
                        id='glifestream.E001',
                    )
                )
    return errors
