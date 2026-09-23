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

/** Shrinks the pictures wider than the stream, now or once they load. */
export function scaledown_images(sel?: string | JQuery): void {
    const maxWidth = ($('#stream').width() as number) - 80;
    const images = typeof sel === 'object' ? $(sel) : $(sel || '#stream img');
    (images as JQuery<HTMLImageElement>).each(function () {
        if (this.complete) {
            if (this.width > maxWidth) {
                this.width = maxWidth;
                if (this.style.width) {
                    const p = (maxWidth * 100) / parseInt(this.style.width, 10);
                    this.style.width = maxWidth + 'px';
                    this.style.height = (this.height * p) / 100 + 'px';
                }
            }
        } else {
            this.onload = function () {
                const img = this as HTMLImageElement;
                if (img.width > maxWidth) {
                    img.width = maxWidth;
                    if (img.style.width) {
                        const p = (maxWidth * 100) / parseInt(img.style.width, 10);
                        img.style.width = maxWidth + 'px';
                        img.style.height = (img.height * p) / 100 + 'px';
                    }
                }
                img.onload = null;
            };
        }
    });
}
