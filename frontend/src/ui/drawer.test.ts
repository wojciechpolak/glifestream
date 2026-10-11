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

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { init_drawer } from './drawer';

const CLOSED = 80;
const OPEN = 500;

let sidebar: HTMLElement;
let handle: HTMLElement;
let content: HTMLElement;
let field: HTMLElement;
/** The time of the next touch event, in ms. */
let now = 0;

function narrow_screen(narrow: boolean): void {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
        matches: narrow,
    } as MediaQueryList);
}

/**
 * Dispatches a touch event of one finger at (x, y), or of none, `after` ms
 * after the one before.
 */
function touch(
    type: string,
    at: [number, number] | null,
    target: EventTarget = handle,
    after = 16,
): Event {
    now += after;
    const event = new Event(type, { bubbles: true, cancelable: true });
    const touches = at ? [{ clientX: at[0], clientY: at[1] }] : [];
    Object.defineProperty(event, 'touches', { value: touches });
    Object.defineProperty(event, 'timeStamp', { value: now });
    target.dispatchEvent(event);
    return event;
}

/** A slow swipe from `from` to `to` along y, in steps of 10px. */
function swipe(from: number, to: number, target: EventTarget = handle): void {
    touch('touchstart', [100, from], target);
    const step = to > from ? 10 : -10;
    for (let y = from + step; step > 0 ? y <= to : y >= to; y += step) {
        touch('touchmove', [100, y], target, 50);
    }
    touch('touchend', null, target, 50);
}

function expanded(): boolean {
    return sidebar.classList.contains('expanded');
}

beforeEach(() => {
    document.body.innerHTML = `
        <aside id="sidebar">
          <button id="sidebar-toggle" aria-expanded="false">Menu</button>
          <section id="about"><p>About</p><input id="search"></section>
        </aside>`;
    sidebar = document.getElementById('sidebar') as HTMLElement;
    handle = document.getElementById('sidebar-toggle') as HTMLElement;
    content = document.getElementById('about') as HTMLElement;
    field = document.getElementById('search') as HTMLElement;
    // As the themes size it: an inline height while dragged, else its state's.
    Object.defineProperty(sidebar, 'offsetHeight', {
        configurable: true,
        get: () =>
            sidebar.style.height
                ? parseFloat(sidebar.style.height)
                : expanded()
                  ? OPEN
                  : CLOSED,
    });
    narrow_screen(true);
    init_drawer(sidebar);
});

afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = '';
});

describe('init_drawer', () => {
    it('opens and closes on a tap of the handle', () => {
        handle.click();
        expect(expanded()).toBe(true);
        expect(handle.getAttribute('aria-expanded')).toBe('true');

        handle.click();
        expect(expanded()).toBe(false);
        expect(handle.getAttribute('aria-expanded')).toBe('false');
    });

    it('opens on a swipe up, following the finger', () => {
        touch('touchstart', [100, 600]);
        const move = touch('touchmove', [100, 450], handle, 50);

        expect(move.defaultPrevented).toBe(true);
        expect(sidebar.classList.contains('dragging')).toBe(true);
        expect(sidebar.style.height).toBe(CLOSED + 150 + 'px');
        expect(expanded()).toBe(false);

        touch('touchmove', [100, 300], handle, 50);
        touch('touchend', null, handle, 50);

        expect(expanded()).toBe(true);
        expect(handle.getAttribute('aria-expanded')).toBe('true');
        expect(sidebar.classList.contains('dragging')).toBe(false);
        expect(sidebar.style.height).toBe('');
    });

    it('stops at its open height', () => {
        touch('touchstart', [100, 700]);
        touch('touchmove', [100, 0], handle, 50);

        expect(sidebar.style.height).toBe(OPEN + 'px');
        touch('touchend', null);
    });

    it('settles back closed after a short, slow swipe', () => {
        swipe(600, 500);

        expect(expanded()).toBe(false);
        expect(sidebar.style.height).toBe('');
    });

    it('opens on a short flick', () => {
        touch('touchstart', [100, 600]);
        touch('touchmove', [100, 580], handle, 10);
        touch('touchmove', [100, 560], handle, 10);
        touch('touchend', null, handle, 10);

        expect(expanded()).toBe(true);
    });

    it('takes no flick from a finger held still before it is lifted', () => {
        touch('touchstart', [100, 600]);
        touch('touchmove', [100, 580], handle, 10);
        touch('touchmove', [100, 560], handle, 10);
        touch('touchend', null, handle, 300);

        expect(expanded()).toBe(false);
    });

    it('closes on a swipe down its handle', () => {
        handle.click();
        swipe(100, 500);

        expect(expanded()).toBe(false);
        expect(handle.getAttribute('aria-expanded')).toBe('false');
    });

    it('closes on a swipe down its content scrolled to the top', () => {
        handle.click();
        swipe(100, 500, content);

        expect(expanded()).toBe(false);
    });

    it('lets its content scrolled down scroll, not close', () => {
        handle.click();
        sidebar.scrollTop = 120;

        touch('touchstart', [100, 100], content);
        const move = touch('touchmove', [100, 400], content, 50);
        touch('touchend', null, content, 50);

        expect(move.defaultPrevented).toBe(false);
        expect(expanded()).toBe(true);
    });

    it('lets its open content scroll on a swipe up', () => {
        handle.click();

        touch('touchstart', [100, 400], content);
        const move = touch('touchmove', [100, 200], content, 50);
        touch('touchend', null, content, 50);

        expect(move.defaultPrevented).toBe(false);
        expect(expanded()).toBe(true);
        expect(sidebar.classList.contains('dragging')).toBe(false);
    });

    it('ignores a swipe down when closed', () => {
        touch('touchstart', [100, 600]);
        const move = touch('touchmove', [100, 700], handle, 50);
        touch('touchend', null);

        expect(move.defaultPrevented).toBe(false);
        expect(expanded()).toBe(false);
        expect(sidebar.classList.contains('dragging')).toBe(false);
    });

    it('ignores a sideways swipe', () => {
        touch('touchstart', [100, 600]);
        touch('touchmove', [300, 560], handle, 50);
        touch('touchmove', [300, 300], handle, 50);
        touch('touchend', null);

        expect(expanded()).toBe(false);
        expect(sidebar.style.height).toBe('');
    });

    it('leaves a touch in a field alone', () => {
        handle.click();

        touch('touchstart', [100, 100], field);
        const move = touch('touchmove', [100, 500], field, 50);
        touch('touchend', null, field);

        expect(move.defaultPrevented).toBe(false);
        expect(expanded()).toBe(true);
    });

    it('does nothing on a wide screen', () => {
        narrow_screen(false);

        swipe(600, 200);

        expect(expanded()).toBe(false);
    });

    it('ignores the click a swipe leaves behind', () => {
        swipe(600, 200);
        handle.click();

        expect(expanded()).toBe(true);

        // The next tap is a tap again.
        touch('touchstart', [100, 100]);
        touch('touchend', null);
        handle.click();
        expect(expanded()).toBe(false);
    });

    it('puts it back as it was on a cancelled swipe', () => {
        touch('touchstart', [100, 600]);
        touch('touchmove', [100, 200], handle, 50);
        touch('touchcancel', null);

        expect(expanded()).toBe(false);
        expect(sidebar.classList.contains('dragging')).toBe(false);
        expect(sidebar.style.height).toBe('');
    });

    it('does nothing on a page without a sidebar', () => {
        expect(() => init_drawer(null)).not.toThrow();
    });
});
