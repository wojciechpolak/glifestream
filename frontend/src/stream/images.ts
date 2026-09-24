/*
 *  gLifestream Copyright (C) 2009-2026 Wojciech Polak
 *
 *  This program is free software; you can redistribute it and/or modify it
 *  under the terms of the GNU General Public License as published by the
 *  Free Software Foundation; either version 3 of the License, or (at your
 *  option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/** The width of the stream's content, inside its padding and border. */
function stream_width(): number {
    const stream = document.getElementById('stream');
    if (!stream) {
        return 0;
    }
    const style = getComputedStyle(stream);
    const edges = [
        style.paddingLeft,
        style.paddingRight,
        style.borderLeftWidth,
        style.borderRightWidth,
    ].reduce((sum, value) => sum + (parseFloat(value) || 0), 0);
    return stream.offsetWidth - edges;
}

function scaledown(img: HTMLImageElement, maxWidth: number): void {
    if (img.width > maxWidth) {
        img.width = maxWidth;
        if (img.style.width) {
            const p = (maxWidth * 100) / parseInt(img.style.width, 10);
            img.style.width = maxWidth + 'px';
            img.style.height = (img.height * p) / 100 + 'px';
        }
    }
}

/** Shrinks the pictures wider than the stream, now or once they load. */
export function scaledown_images(
    images: Iterable<HTMLImageElement> = document.querySelectorAll('#stream img'),
): void {
    const maxWidth = stream_width() - 80;
    for (const img of images) {
        if (img.complete) {
            scaledown(img, maxWidth);
        } else {
            img.addEventListener('load', () => scaledown(img, maxWidth), {
                once: true,
            });
        }
    }
}
