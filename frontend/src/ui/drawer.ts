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

import { listen } from '../util/dom';

// The sidebar's drawer. At 640px and below the themes pin the sidebar to the
// bottom of the screen, closed to its handle; a tap on the handle opens or
// closes it, and so does a swipe: up on the closed drawer, down on its
// handle or on its content scrolled to the top. The drawer follows the
// finger, as .dragging, and settles open or closed when it is let go.
// A touch that starts in the drawer is the drawer's, never a pull to
// refresh (ui/pull-to-refresh.ts).

/** The screens on which the sidebar is a drawer, as the themes have it. */
const NARROW = '(max-width: 640px)';
/** How far a finger moves before it is a swipe, not a tap. */
const SLOP = 8;
/** A swipe faster than this, in px/ms, settles the drawer its way. */
const FLICK = 0.4;
/** A finger held still this long, in ms, before it is lifted makes no flick. */
const FLICK_HOLD = 100;
/** How long after a swipe the click it may leave behind is ignored, in ms. */
const CLICK_GRACE = 500;

const IGNORED = 'input, textarea, select, [contenteditable="true"]';

interface Drag {
    startX: number;
    startY: number;
    expanded: boolean;
    dragging: boolean;
    height: number;
    current: number;
    closed: number;
    open: number;
    lastY: number;
    lastTime: number;
    velocity: number;
}

/** Opens or closes the drawer, and tells its handle. */
function set_drawer_expanded(sidebar: HTMLElement, expanded: boolean): void {
    sidebar.classList.toggle('expanded', expanded);
    sidebar
        .querySelector('#sidebar-toggle')
        ?.setAttribute('aria-expanded', String(expanded));
}

function is_narrow(): boolean {
    return (
        typeof (window as Partial<Window>).matchMedia === 'function' &&
        window.matchMedia(NARROW).matches
    );
}

/** The drawer's height open and closed, as the theme makes it. */
function measure(sidebar: HTMLElement, expanded: boolean): [number, number] {
    const now = sidebar.offsetHeight;
    sidebar.classList.toggle('expanded', !expanded);
    const other = sidebar.offsetHeight;
    sidebar.classList.toggle('expanded', expanded);
    return expanded ? [other, now] : [now, other];
}

/** Whether a touch may start a swipe: one finger, on a phone, not in a field. */
function can_start_swipe(
    event: TouchEvent,
    drawer: HTMLElement,
    handle: HTMLElement | null,
): boolean {
    const target = event.target as Partial<Element> | null;
    if (event.touches.length !== 1 || !is_narrow() || target?.closest?.(IGNORED)) {
        return false;
    }
    // Open content scrolled down scrolls back up first.
    const on_handle = !!handle && handle.contains(target as Node);
    return !drawer.classList.contains('expanded') || on_handle || drawer.scrollTop <= 0;
}

/**
 * What a finger moved by (dx, dy) means: too little to tell yet, a swipe
 * of the drawer, or not one: sideways, or towards where the drawer already is.
 */
function swipe_intent(drag: Drag, dx: number, dy: number): 'wait' | 'drag' | 'drop' {
    if (Math.abs(dx) < SLOP && Math.abs(dy) < SLOP) {
        return 'wait';
    }
    return Math.abs(dx) > Math.abs(dy) || dy > 0 !== drag.expanded ? 'drop' : 'drag';
}

/** Notes how fast the finger moves, for a flick. */
function track(drag: Drag, y: number, time: number): void {
    const elapsed = time - drag.lastTime;
    if (elapsed > 0) {
        drag.velocity = (y - drag.lastY) / elapsed;
    }
    drag.lastY = y;
    drag.lastTime = time;
}

/** Lets the handle of `sidebar` open and close it, by a tap or a swipe. */
export function init_drawer(
    sidebar: HTMLElement | null = document.getElementById('sidebar'),
): void {
    if (!sidebar) {
        return;
    }
    const drawer = sidebar;
    const handle = drawer.querySelector<HTMLElement>('#sidebar-toggle');
    let drag: Drag | null = null;
    let ignore_clicks_until = 0;

    listen(handle, 'click', function () {
        set_drawer_expanded(drawer, !drawer.classList.contains('expanded'));
    });

    // A swipe on the handle can end in a click; it must not undo the swipe.
    drawer.addEventListener(
        'click',
        function (event) {
            if (Date.now() < ignore_clicks_until) {
                ignore_clicks_until = 0;
                event.preventDefault();
                event.stopPropagation();
            }
        },
        true,
    );

    function settle(expanded: boolean): void {
        drawer.classList.remove('dragging');
        drawer.style.removeProperty('height');
        set_drawer_expanded(drawer, expanded);
    }

    drawer.addEventListener(
        'touchstart',
        function (event) {
            drag = null;
            ignore_clicks_until = 0;
            if (!can_start_swipe(event, drawer, handle)) {
                return;
            }
            const touch = event.touches[0] as Touch;
            drag = {
                startX: touch.clientX,
                startY: touch.clientY,
                expanded: drawer.classList.contains('expanded'),
                dragging: false,
                height: 0,
                current: 0,
                closed: 0,
                open: 0,
                lastY: touch.clientY,
                lastTime: event.timeStamp,
                velocity: 0,
            };
        },
        { passive: true },
    );

    drawer.addEventListener(
        'touchmove',
        function (event) {
            if (!drag || event.touches.length !== 1) {
                return;
            }
            const touch = event.touches[0] as Touch;
            const dx = touch.clientX - drag.startX;
            const dy = touch.clientY - drag.startY;

            if (!drag.dragging) {
                const intent = swipe_intent(drag, dx, dy);
                if (intent !== 'drag') {
                    if (intent === 'drop') {
                        drag = null;
                    }
                    return;
                }
                drag.dragging = true;
                drawer.classList.add('dragging');
                drag.height = drawer.offsetHeight;
                [drag.closed, drag.open] = measure(drawer, drag.expanded);
            }

            if (event.cancelable) {
                event.preventDefault();
            }
            track(drag, touch.clientY, event.timeStamp);
            drag.current = Math.min(drag.open, Math.max(drag.closed, drag.height - dy));
            drawer.style.height = drag.current + 'px';
        },
        { passive: false },
    );

    drawer.addEventListener(
        'touchend',
        function (event) {
            const ended = drag;
            drag = null;
            if (!ended?.dragging) {
                return;
            }
            const velocity =
                event.timeStamp - ended.lastTime > FLICK_HOLD ? 0 : ended.velocity;
            const expanded =
                velocity < -FLICK
                    ? true
                    : velocity > FLICK
                      ? false
                      : ended.current > (ended.closed + ended.open) / 2;
            ignore_clicks_until = Date.now() + CLICK_GRACE;
            settle(expanded);
        },
        { passive: true },
    );

    drawer.addEventListener(
        'touchcancel',
        function () {
            const cancelled = drag;
            drag = null;
            if (cancelled?.dragging) {
                settle(cancelled.expanded);
            }
        },
        { passive: true },
    );
}
