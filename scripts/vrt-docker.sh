#!/bin/bash
#
# vrt-docker.sh
#
# gLifestream Copyright (C) 2026 Wojciech Polak
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.
#

set -eu

mode="${1:-compare}"
shift || true
image="gls-vrt:1.58.0-noble"
workdir="$(pwd)"
uv_project_dir="$workdir/run/vrt-venv"
uv_cache_dir="$workdir/run/vrt-uv-cache"
uv_home_dir="$workdir/run/vrt-home"
vrt_command="./scripts/vrt.sh"

mkdir -p "$uv_project_dir" "$uv_cache_dir" "$uv_home_dir"

case "$mode" in
  compare)
    ;;
  baseline)
    vrt_command="./scripts/vrt-baseline.sh"
    ;;
  *)
    echo "usage: $0 [compare|baseline]" >&2
    exit 1
    ;;
esac

if ! docker image inspect "$image" >/dev/null 2>&1; then
  docker build -f scripts/vrt.Dockerfile -t "$image" .
fi

docker run --rm --init --ipc=host \
  -e CI=1 \
  -e HOME="/work/run/vrt-home" \
  -e VRT=1 \
  -e UV_CACHE_DIR="/work/run/vrt-uv-cache" \
  -e UV_PROJECT_ENVIRONMENT="/work/run/vrt-venv" \
  -v "$workdir":/work \
  -w /work \
  "$image" \
  bash -lc 'set -eu
    python3 scripts/vrt-make-settings.py --site-root /work/glifestream --secret-key ci-secret-key --output /tmp/vrt_settings.py
    export PYTHONPATH="/tmp:${PYTHONPATH:-}"
    export DJANGO_SETTINGS_MODULE=vrt_settings
    exec "$@"' bash "$vrt_command" "$@"
