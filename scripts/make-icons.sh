#!/bin/bash
#
# Render the logo, icons and social preview from their SVG sources.
# Needs resvg and magick (ImageMagick).

set -eu
cd "$(dirname "$0")/.."

static=glifestream/static
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

for n in 16 32 48; do
    resvg -w $n -h $n docs/assets/favicon.svg "$tmp/$n.png"
done
magick "$tmp/16.png" "$tmp/32.png" "$tmp/48.png" $static/favicon.ico

# Apple and maskable icons are full-bleed: the platform cuts the shape.
resvg -w 180 -h 180 docs/assets/app-icon.svg $static/apple-touch-icon.png
resvg -w 512 -h 512 docs/assets/app-icon.svg $static/icon-maskable-512.png
for f in apple-touch-icon icon-maskable-512; do
    magick $static/$f.png -alpha off $static/$f.png
done
resvg -w 192 -h 192 docs/assets/logo.svg $static/icon-192.png
resvg -w 512 -h 512 docs/assets/logo.svg $static/icon-512.png

resvg -w 1280 -h 640 docs/assets/social-preview.svg docs/assets/social-preview.png
magick docs/assets/social-preview.png -alpha off docs/assets/social-preview.png
