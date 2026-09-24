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

import pytest
from django.core.management import call_command
from django.core.management.base import SystemCheckError

from glifestream.gls_staticfiles import GlsSASSCompiler, check_pipeline_sources


def _pipeline(settings, *paths: str) -> None:
    settings.PIPELINE = {
        **settings.PIPELINE,
        'JAVASCRIPT': {
            'main': {'source_filenames': paths, 'output_filename': 'js/main.js'}
        },
        'STYLESHEETS': {},
    }


def test_bundle_sources_that_exist_pass(settings):
    _pipeline(settings, 'favicon.ico', 'js/*.nothing')

    assert check_pipeline_sources() == []


def test_a_missing_built_file_asks_for_the_frontend_build(settings):
    _pipeline(settings, 'favicon.ico', 'js/dist/missing.js')

    [error] = check_pipeline_sources()

    assert error.id == 'glifestream.E001'
    assert "'main'" in error.msg and 'js/dist/missing.js' in error.msg
    assert error.hint == 'Build it with `npm ci && npm run build`.'


def test_a_missing_vendor_file_has_no_build_hint(settings):
    _pipeline(settings, 'js/missing.js')

    [error] = check_pipeline_sources()

    assert error.hint is None


def test_collectstatic_stops_on_a_missing_source(settings, tmp_path):
    _pipeline(settings, 'js/dist/missing.js')
    settings.STATIC_ROOT = str(tmp_path)

    with pytest.raises(SystemCheckError, match='glifestream.E001'):
        call_command('collectstatic', interactive=False, verbosity=0, skip_checks=False)


def test_sass_compiler_writes_only_to_the_directory_it_creates(tmp_path):
    sources = tmp_path / 'src'
    sources.mkdir()
    (sources / '_colors.scss').write_text('$c: red;\n')
    (sources / 'theme.scss').write_text('@import "colors";\n.x { color: $c; }\n')
    output = tmp_path / 'themes' / 'default' / 'style.css'

    GlsSASSCompiler(verbose=False, storage=None).compile_file(
        str(sources / 'theme.scss'), str(output)
    )

    assert 'color: red' in output.read_text()
    assert sorted(p.name for p in sources.iterdir()) == ['_colors.scss', 'theme.scss']
