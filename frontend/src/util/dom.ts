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

/** A child for DCE(): text is set as innerHTML, false and undefined skipped. */
export type DceContent = Node | string | number | false | undefined;

/** Creates an element, sets its properties and appends its content. */
export function DCE<K extends keyof HTMLElementTagNameMap>(
    name: K,
    props?: Record<string, unknown>,
    content_list?: DceContent[],
): HTMLElementTagNameMap[K] {
    const obj = document.createElement(name);
    if (props) {
        const target = obj as unknown as Record<string, unknown>;
        for (const p in props) {
            if (p === 'style') {
                const style = props[p] as Record<string, string>;
                const target_style = obj.style as unknown as Record<string, string>;
                for (const s in style) {
                    target_style[s] = style[s] as string;
                }
            } else {
                target[p] = props[p];
            }
        }
    }
    if (content_list) {
        for (let i = 0; i < content_list.length; i++) {
            const content = content_list[i];
            if (typeof content == 'string' || typeof content == 'number') {
                obj.innerHTML = String(content);
            } else if (typeof content == 'object') {
                obj.appendChild(content);
            }
        }
    }
    return obj;
}

/** Sets window.<ns> to `p`, creating the objects on the way. */
export function es(ns: string, p: unknown): void {
    const t = ns.split(/\./);
    let win = window as unknown as Record<string, unknown>;
    for (let i = 0; i < t.length - 1; i++) {
        const key = t[i] as string;
        if (typeof win[key] == 'undefined') {
            win[key] = {};
        }
        win = win[key] as Record<string, unknown>;
    }
    win[t[t.length - 1] as string] = p;
}

export interface WinGeometry {
    width: number;
    height: number;
    left: number;
    top: number;
}

export const MDOM = {
    /** Centres an absolutely positioned element in the viewport. */
    center: function (
        obj: HTMLElement,
        objWidth?: number | string,
        objHeight?: number | string,
    ): void {
        let innerWidth = 0;
        let innerHeight = 0;
        if (!objWidth && !objHeight) {
            objWidth = $(obj).width() as number | string | undefined;
            objHeight = $(obj).height() as number | string | undefined;
            if (objWidth === '0px' || objWidth === 'auto') {
                objWidth = obj.offsetWidth + 'px';
                objHeight = obj.offsetHeight + 'px';
            }
            if ((objHeight as string).indexOf('px') === -1) {
                obj.style.display = 'block';
                objHeight = obj.clientHeight;
            }
            objWidth = parseInt(objWidth as string);
            objHeight = parseInt(objHeight as string);
        }
        if (window.innerWidth) {
            innerWidth = window.innerWidth / 2;
            innerHeight = window.innerHeight / 2;
        } else if (document.body.clientWidth) {
            innerWidth = ($(window).width() as number) / 2;
            innerHeight = ($(window).height() as number) / 2;
        }
        let wleft = innerWidth - (objWidth as number) / 2;
        if (wleft < 0) {
            wleft = 0;
        }
        obj.style.left = wleft + 'px';
        obj.style.top =
            ($(document).scrollTop() as number) +
            innerHeight -
            (objHeight as number) / 2 +
            'px';
        if (parseInt(obj.style.top) < 1) {
            obj.style.top = '1px';
        }
    },

    /** The geometry of a popup window centred on this one. */
    get_win_center: function (width: number, height: number): WinGeometry {
        const screenX =
            typeof window.screenX !== 'undefined' ? window.screenX : window.screenLeft;
        const screenY =
            typeof window.screenY !== 'undefined' ? window.screenY : window.screenTop;
        const outerWidth =
            typeof window.outerWidth !== 'undefined'
                ? window.outerWidth
                : document.body.clientWidth;
        const outerHeight =
            typeof window.outerHeight !== 'undefined'
                ? window.outerHeight
                : document.body.clientHeight - 22;
        return {
            width: width,
            height: height,
            left: parseInt(String(screenX + (outerWidth - width) / 2), 10),
            top: parseInt(String(screenY + (outerHeight - height) / 2.5), 10),
        };
    },
};
