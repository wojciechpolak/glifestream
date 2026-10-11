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

import os
from glob import has_magic
from typing import Any

from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.apps import StaticFilesConfig
from django.core.checks import CheckMessage, Error, Tags, register
from pipeline.compilers.sass import SASSCompiler
from pipeline.conf import settings as pipeline_settings

from glifestream.settings_themes import THEME_NAME


class GlsStaticFilesConfig(StaticFilesConfig):
    ignore_patterns = [
        '.*',
        '*~',
        '*.scss',
    ]

    def ready(self) -> None:
        super().ready()
        register(check_pipeline_sources, Tags.staticfiles)
        register(check_themes)


class GlsSASSCompiler(SASSCompiler):
    """Pipeline's SASS compiler, run from the directory it writes to.

    collectstatic skips *.scss, so a theme directory that holds nothing else
    is missing from STATIC_ROOT, and sassc does not create it. Pipeline also
    keeps the compiler's output in a temporary file in its working directory;
    among the sources, a collectstatic running at the same time, as the next
    browser test's does, would pick it up just before it goes.
    """

    def compile_file(
        self, infile: str, outfile: str, outdated: bool = False, force: bool = False
    ) -> Any:
        output_dir = os.path.dirname(outfile)
        os.makedirs(output_dir, exist_ok=True)
        command = (pipeline_settings.SASS_BINARY, pipeline_settings.SASS_ARGUMENTS)
        return self.execute_command((*command, infile, outfile), cwd=output_dir)


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
                        hint=_missing_source_hint(path),
                        id='glifestream.E001',
                    )
                )
    return errors


def _missing_source_hint(path: str) -> str | None:
    if path.startswith('js/dist/'):
        return 'Build it with `npm ci && npm run build`.'
    if path.startswith('themes/'):
        return (
            'Put the theme in RUN_DIR/static/themes/<name>/, or take it out of THEMES.'
        )
    return None


def check_themes(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """THEMES names at least one theme, each by a name it can go by, and
    DEFAULT_THEME, when set, is one of them."""
    themes = tuple(settings.THEMES)
    default = getattr(settings, 'DEFAULT_THEME', '')
    if not themes:
        return [
            Error(
                'THEMES names no theme.',
                hint="Leave THEMES unset, or name one, such as 'default'.",
                id='glifestream.E002',
            )
        ]
    errors: list[CheckMessage] = [
        Error(
            f'The theme name {name!r} is not one a theme can go by.',
            hint='Use lowercase letters, digits, "-" and "_".',
            id='glifestream.E003',
        )
        for name in themes
        if not isinstance(name, str) or not THEME_NAME.match(name)
    ]
    if default and default not in themes:
        errors.append(
            Error(
                f'DEFAULT_THEME is {default!r}, which THEMES does not name.',
                hint=f'Pick one of {", ".join(map(str, themes))}, or add it to THEMES.',
                id='glifestream.E004',
            )
        )
    return errors
