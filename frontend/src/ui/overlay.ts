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

let visible = false;
let ovl: HTMLDivElement | null = null;

/** Dims the page behind a dialog; `level` is the opacity in percent. */
function enable(level?: number | string): void {
    if (typeof level === 'undefined') {
        level = '80';
    }
    if (visible) {
        return;
    }
    ovl = document.createElement('div');
    if (ovl) {
        const dh = $(document).height() as number;
        const wh = $(window).height() as number;
        ovl.id = 'overlay';
        ovl.style.position = 'absolute';
        ovl.style.width = '100%';
        ovl.style.height = (dh > wh ? dh : wh) + 'px';
        ovl.style.top = '0';
        ovl.style.left = '0';
        ovl.style.backgroundColor = 'black';
        ovl.style.opacity = '0.' + level;
        ovl.style.filter = 'alpha(opacity=' + level + ')';
        ovl.style.zIndex = '1000';
        ovl.style.display = 'block';
        document.body.appendChild(ovl);
        visible = true;
    }
}

function disable(): void {
    if (ovl) {
        document.body.removeChild(ovl);
        visible = false;
    }
}

export const Overlay = { enable, disable };
