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

import { pinned_head_height, scroll_to_element } from './scroll';

function rect(top: number, bottom: number): DOMRect {
    return {
        top,
        bottom,
        left: 0,
        right: 0,
        width: 0,
        height: bottom - top,
    } as DOMRect;
}

let scrolled: ScrollToOptions[];

beforeEach(() => {
    document.body.innerHTML = '<header id="head"></header><article></article>';
    scrolled = [];
    window.scrollTo = vi.fn((options: ScrollToOptions) => {
        scrolled.push(options);
    }) as typeof window.scrollTo;
    document.querySelector('article')!.getBoundingClientRect = () => rect(500, 600);
    document.getElementById('head')!.getBoundingClientRect = () => rect(0, 52);
});

afterEach(() => {
    document.body.innerHTML = '';
});

describe('scroll_to_element', () => {
    it('leaves the offset above the element', () => {
        scroll_to_element(document.querySelector('article')!, 24);
        expect(scrolled[0]?.top).toBe(476);
        expect(pinned_head_height()).toBe(0);
    });

    it('keeps the element clear of a pinned top bar', () => {
        document.getElementById('head')!.style.position = 'fixed';
        expect(pinned_head_height()).toBe(52);
        scroll_to_element(document.querySelector('article')!, 24);
        expect(scrolled[0]?.top).toBe(424);
    });

    it('counts nothing without a top bar', () => {
        document.getElementById('head')!.remove();
        expect(pinned_head_height()).toBe(0);
    });
});
