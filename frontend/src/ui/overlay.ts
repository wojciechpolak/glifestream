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

let ovl: HTMLDivElement | null = null;

function page_height(): number {
    const body = document.body;
    const html = document.documentElement;
    return Math.max(
        body.scrollHeight,
        html.scrollHeight,
        body.offsetHeight,
        html.offsetHeight,
        html.clientHeight,
    );
}

/** Dims the page behind a dialog; `level` is the opacity in percent. */
function enable(level: number = 80): void {
    if (ovl) {
        return;
    }
    ovl = document.createElement('div');
    ovl.id = 'overlay';
    Object.assign(ovl.style, {
        position: 'absolute',
        width: '100%',
        height: page_height() + 'px',
        top: '0',
        left: '0',
        backgroundColor: 'black',
        opacity: String(level / 100),
        zIndex: '1000',
        display: 'block',
    });
    document.body.appendChild(ovl);
}

function disable(): void {
    if (ovl) {
        ovl.remove();
        ovl = null;
    }
}

export const Overlay = { enable, disable };
