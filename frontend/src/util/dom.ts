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

/** A child for h(): a string becomes text; false, null and undefined are skipped. */
export type Child = Node | string | number | false | null | undefined;

/** The properties h() sets; `style` is merged into the element's style. */
export type Props<K extends keyof HTMLElementTagNameMap> = Partial<
    Omit<HTMLElementTagNameMap[K], 'style'>
> & { style?: Partial<CSSStyleDeclaration> };

/** Creates an element, sets its properties and appends its children. */
export function h<K extends keyof HTMLElementTagNameMap>(
    name: K,
    props?: Props<K> | null,
    children?: Child[],
): HTMLElementTagNameMap[K] {
    const el = document.createElement(name);
    if (props) {
        const { style, ...rest } = props;
        Object.assign(el, rest);
        if (style) {
            Object.assign(el.style, style);
        }
    }
    for (const child of children || []) {
        if (child === false || child === null || child === undefined) {
            continue;
        }
        el.append(typeof child === 'number' ? String(child) : child);
    }
    return el;
}

/**
 * A handler of the element it listens on, or of the element a delegated
 * event came from. As with jQuery, returning false cancels the event and
 * stops it.
 */
export type Handler<T, E extends Event> = (target: T, event: E) => boolean | void;

function run_handler<T, E extends Event>(
    handler: Handler<T, E>,
    target: T,
    event: E,
): void {
    if (handler(target, event) === false) {
        event.preventDefault();
        event.stopPropagation();
    }
}

/** Listens on every element `selector` finds, or on the element given. */
export function listen<K extends keyof HTMLElementEventMap>(
    target: string | HTMLElement | null,
    type: K,
    handler: Handler<HTMLElement, HTMLElementEventMap[K]>,
): void {
    const elements =
        typeof target === 'string'
            ? document.querySelectorAll<HTMLElement>(target)
            : target
              ? [target]
              : [];
    for (const el of elements) {
        el.addEventListener(type, (event) => run_handler(handler, el, event));
    }
}

/**
 * Listens on `root` for events from inside elements that match `selector`;
 * the handler gets the element, also when it was added later.
 */
export function delegate<K extends keyof HTMLElementEventMap>(
    root: HTMLElement | Document,
    type: K,
    selector: string,
    handler: Handler<HTMLElement, HTMLElementEventMap[K]>,
): void {
    root.addEventListener(type, function (event) {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        const matched = target.closest<HTMLElement>(selector);
        if (matched && root.contains(matched)) {
            run_handler(handler, matched, event as HTMLElementEventMap[K]);
        }
    });
}

/** Submits a form, even one with a field named `submit` hiding the method. */
export function submit_form(form: HTMLFormElement): void {
    HTMLFormElement.prototype.submit.call(form);
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

interface WinGeometry {
    width: number;
    height: number;
    left: number;
    top: number;
}

export const MDOM = {
    /** Centres an absolutely positioned element in the viewport. */
    center: function (obj: HTMLElement, width: number, height: number): void {
        const left = Math.max(0, window.innerWidth / 2 - width / 2);
        const top = window.scrollY + window.innerHeight / 2 - height / 2;
        obj.style.left = left + 'px';
        obj.style.top = Math.max(1, top) + 'px';
    },

    /** The geometry of a popup window centred on this one. */
    get_win_center: function (width: number, height: number): WinGeometry {
        return {
            width: width,
            height: height,
            left: Math.trunc(window.screenX + (window.outerWidth - width) / 2),
            top: Math.trunc(window.screenY + (window.outerHeight - height) / 2.5),
        };
    },
};
