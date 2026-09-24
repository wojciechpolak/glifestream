/*
 *  gLifestream Copyright (C) 2026 Wojciech Polak
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

// Showing and hiding with the effects the jQuery script used: fades and
// slides, run with the Web Animations API. Each returns a promise that
// settles once the element is in its final state. They are instant when the
// reader prefers reduced motion, as the stylesheet's transitions are.

/** jQuery's default, 'normal', duration. */
export const NORMAL = 400;
export const FAST = 200;

interface Running {
    animation: Animation;
    finish: () => void;
}

const running = new WeakMap<HTMLElement, Running>();
const shown_display = new WeakMap<HTMLElement, string>();
const default_displays = new Map<string, string>();

export function reduced_motion(): boolean {
    return (
        typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches
    );
}

/** Whether the element is rendered: in the page, and nothing up to it has display none. */
export function is_visible(el: Element): boolean {
    if (!el.isConnected) {
        return false;
    }
    for (let node: Element | null = el; node; node = node.parentElement) {
        if (getComputedStyle(node).display === 'none') {
            return false;
        }
    }
    return true;
}

/** The display an element of this tag has when nothing hides it. */
function default_display(tag: string): string {
    let display = default_displays.get(tag);
    if (display === undefined) {
        const probe = document.createElement(tag);
        document.body.appendChild(probe);
        display = getComputedStyle(probe).display;
        probe.remove();
        if (!display || display === 'none') {
            display = 'block';
        }
        default_displays.set(tag, display);
    }
    return display;
}

/** Shows an element hidden inline or by the stylesheet. */
export function show(el: HTMLElement): void {
    stop(el);
    if (el.style.display === 'none') {
        el.style.display = shown_display.get(el) || '';
    }
    if (getComputedStyle(el).display === 'none') {
        el.style.display = default_display(el.tagName);
    }
}

export function hide(el: HTMLElement): void {
    stop(el);
    const display = getComputedStyle(el).display;
    if (display !== 'none') {
        shown_display.set(el, el.style.display);
    }
    el.style.display = 'none';
}

/** Shows or hides; without `visible`, flips what is visible now. */
export function toggle(el: HTMLElement, visible?: boolean): void {
    if (visible ?? !is_visible(el)) {
        show(el);
    } else {
        hide(el);
    }
}

/** Jumps the element's running effect to its end. */
export function stop(el: HTMLElement): void {
    const current = running.get(el);
    if (current) {
        running.delete(el);
        current.animation.cancel();
        current.finish();
    }
}

function animate(
    el: HTMLElement,
    keyframes: Keyframe[],
    duration: number,
    done: () => void,
): Promise<void> {
    return new Promise(function (resolve) {
        function finish(): void {
            done();
            resolve();
        }
        if (duration <= 0 || reduced_motion() || typeof el.animate !== 'function') {
            finish();
            return;
        }
        const animation = el.animate(keyframes, { duration, easing: 'ease-in-out' });
        const entry = { animation, finish };
        running.set(el, entry);
        animation.addEventListener('finish', function () {
            if (running.get(el) === entry) {
                running.delete(el);
                finish();
            }
        });
    });
}

export function fade_in(el: HTMLElement, duration = NORMAL): Promise<void> {
    if (is_visible(el) && !running.has(el)) {
        return Promise.resolve();
    }
    show(el);
    const opacity = getComputedStyle(el).opacity;
    return animate(el, [{ opacity: 0 }, { opacity }], duration, () => {});
}

export function fade_out(el: HTMLElement, duration = NORMAL): Promise<void> {
    if (!is_visible(el)) {
        return Promise.resolve();
    }
    stop(el);
    const opacity = getComputedStyle(el).opacity;
    return animate(el, [{ opacity }, { opacity: 0 }], duration, () => hide(el));
}

const SLIDE_PROPERTIES = [
    'height',
    'paddingTop',
    'paddingBottom',
    'marginTop',
    'marginBottom',
] as const;

/** The element's box as a keyframe, or collapsed to nothing. */
function box_keyframe(el: HTMLElement, collapsed: boolean): Keyframe {
    const style = getComputedStyle(el);
    const frame: Keyframe = { overflow: 'hidden' };
    for (const property of SLIDE_PROPERTIES) {
        frame[property] = collapsed ? '0px' : style[property];
    }
    return frame;
}

export function slide_down(el: HTMLElement, duration = NORMAL): Promise<void> {
    if (is_visible(el) && !running.has(el)) {
        return Promise.resolve();
    }
    show(el);
    const frames = [box_keyframe(el, true), box_keyframe(el, false)];
    return animate(el, frames, duration, () => {});
}

export function slide_up(el: HTMLElement, duration = NORMAL): Promise<void> {
    if (!is_visible(el)) {
        return Promise.resolve();
    }
    stop(el);
    const frames = [box_keyframe(el, false), box_keyframe(el, true)];
    return animate(el, frames, duration, () => hide(el));
}
