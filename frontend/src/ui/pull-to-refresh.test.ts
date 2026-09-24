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

import { init_pull_to_refresh } from './pull-to-refresh';

/** The listeners the tested code added to the document, removed after each test. */
const added: [string, EventListenerOrEventListenerObject][] = [];
const reload = vi.fn();

function narrow_screen(narrow: boolean): void {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
        matches: narrow,
    } as MediaQueryList);
}

/** Dispatches a touch event of one finger at (x, y), or of none. */
function touch(
    type: string,
    at: [number, number] | null,
    target: EventTarget = document.body,
): Event {
    const event = new Event(type, { bubbles: true, cancelable: true });
    const touches = at ? [{ clientX: at[0], clientY: at[1] }] : [];
    Object.defineProperty(event, 'touches', { value: touches });
    target.dispatchEvent(event);
    return event;
}

function indicator(): HTMLElement {
    return document.getElementById('pull-to-refresh') as HTMLElement;
}

function body_classes(): string[] {
    return Array.from(document.body.classList);
}

beforeEach(() => {
    const add = document.addEventListener.bind(document);
    vi.spyOn(document, 'addEventListener').mockImplementation(
        (type, listener, options) => {
            added.push([type, listener]);
            add(type, listener, options);
        },
    );
    window.__glsReloadHandler = reload;
    document.body.innerHTML = '<section id="stream"></section><input id="field">';
    narrow_screen(true);
});

afterEach(() => {
    for (const [type, listener] of added.splice(0)) {
        document.removeEventListener(type, listener);
    }
    vi.restoreAllMocks();
    vi.useRealTimers();
    reload.mockReset();
    delete window.__glsReloadHandler;
    document.body.className = '';
    document.body.removeAttribute('style');
    document.body.innerHTML = '';
});

describe('init_pull_to_refresh', () => {
    it('does nothing on a wide screen', () => {
        narrow_screen(false);

        init_pull_to_refresh();

        expect(indicator()).toBeNull();
    });

    it('does nothing on a page without a stream', () => {
        document.body.innerHTML = '';

        init_pull_to_refresh();

        expect(indicator()).toBeNull();
    });

    it('reloads the page after a long enough pull', () => {
        vi.useFakeTimers();
        init_pull_to_refresh();

        touch('touchstart', [10, 0]);
        const move = touch('touchmove', [10, 200]);

        expect(move.defaultPrevented).toBe(true);
        expect(body_classes()).toEqual(['pull-refresh-active', 'pull-refresh-armed']);
        expect(indicator().textContent).toBe('Release to refresh');
        expect(document.body.style.getPropertyValue('--pull-refresh-offset')).toBe(
            '84px',
        );

        touch('touchend', null);

        expect(indicator().textContent).toBe('Refreshing...');
        expect(body_classes()).toEqual([
            'pull-refresh-active',
            'pull-refresh-refreshing',
        ]);
        vi.runAllTimers();
        expect(reload).toHaveBeenCalledOnce();

        // A refresh on its way is not restarted or undone.
        touch('touchstart', [10, 0]);
        touch('touchcancel', null);
        expect(body_classes()).toContain('pull-refresh-refreshing');
    });

    it('lets go of a short pull', () => {
        init_pull_to_refresh();

        touch('touchstart', [10, 0]);
        touch('touchmove', [10, 30]);

        expect(body_classes()).toEqual(['pull-refresh-active']);
        expect(indicator().textContent).toBe('Pull to refresh');

        touch('touchend', null);

        expect(body_classes()).toEqual([]);
        expect(document.body.style.getPropertyValue('--pull-refresh-offset')).toBe(
            '0px',
        );
        expect(reload).not.toHaveBeenCalled();
    });

    it('lets go of a pull that turns sideways', () => {
        init_pull_to_refresh();

        touch('touchstart', [10, 0]);
        touch('touchmove', [10, 200]);
        const move = touch('touchmove', [100, 200]);
        touch('touchend', null);

        expect(move.defaultPrevented).toBe(false);
        expect(body_classes()).toEqual([]);
        expect(reload).not.toHaveBeenCalled();
    });

    it('leaves a touch in a field alone', () => {
        init_pull_to_refresh();

        touch('touchstart', [10, 0], document.getElementById('field') as HTMLElement);
        const move = touch('touchmove', [10, 200]);

        expect(move.defaultPrevented).toBe(false);
        expect(body_classes()).toEqual([]);
    });

    it('ignores a touch of two fingers', () => {
        init_pull_to_refresh();

        const event = new Event('touchstart', { bubbles: true });
        Object.defineProperty(event, 'touches', { value: [{}, {}] });
        document.body.dispatchEvent(event);
        touch('touchmove', [10, 200]);

        expect(body_classes()).toEqual([]);
    });

    it('lets go of a cancelled pull', () => {
        init_pull_to_refresh();

        touch('touchstart', [10, 0]);
        touch('touchmove', [10, 200]);
        touch('touchcancel', null);

        expect(body_classes()).toEqual([]);
        expect(indicator().textContent).toBe('Pull to refresh');
    });
});
