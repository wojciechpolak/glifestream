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

import { afterEach, describe, expect, it, vi } from 'vitest';

import { init_sidebar_height } from './sidebar-height';

/** A sidebar `height` pixels tall, as the layout would make it. */
function sidebar(height: number): HTMLElement {
    const el = document.createElement('aside');
    Object.defineProperty(el, 'offsetHeight', {
        configurable: true,
        get: () => height,
    });
    return el;
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('init_sidebar_height', () => {
    it('tells the theme how tall the sidebar is', () => {
        const el = sidebar(950);
        init_sidebar_height(el);
        expect(el.style.getPropertyValue('--sidebar-height')).toBe('950px');
    });

    it('tells it again when the sidebar changes size', () => {
        let observed: (() => void) | null = null;
        vi.stubGlobal(
            'ResizeObserver',
            class {
                constructor(callback: () => void) {
                    observed = callback;
                }
                observe(): void {}
            },
        );
        let height = 700;
        const el = document.createElement('aside');
        Object.defineProperty(el, 'offsetHeight', { get: () => height });

        init_sidebar_height(el);
        height = 1200;
        (observed as unknown as () => void)();

        expect(el.style.getPropertyValue('--sidebar-height')).toBe('1200px');
    });

    it('does nothing on a page without a sidebar', () => {
        expect(() => init_sidebar_height(null)).not.toThrow();
    });
});
