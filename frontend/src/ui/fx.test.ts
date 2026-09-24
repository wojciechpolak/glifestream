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

import { fade_in, fade_out, hide, is_visible, show, slide_up, toggle } from './fx';

function reduce_motion(reduce: boolean): void {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
        matches: reduce,
    } as MediaQueryList);
}

beforeEach(() => {
    reduce_motion(true);
    document.head.innerHTML = '<style>.hidden-by-css { display: none; }</style>';
});

afterEach(() => {
    vi.restoreAllMocks();
    document.head.innerHTML = '';
    document.body.innerHTML = '';
});

/** An animation that finishes when the test dispatches 'finish'. */
function fake_animation(): Animation & { cancel: ReturnType<typeof vi.fn> } {
    return Object.assign(new EventTarget(), {
        cancel: vi.fn(),
    }) as unknown as Animation & {
        cancel: ReturnType<typeof vi.fn>;
    };
}

function element(html: string): HTMLElement {
    document.body.insertAdjacentHTML('beforeend', html);
    return document.body.lastElementChild as HTMLElement;
}

describe('is_visible', () => {
    it('is false when the element or a parent is not displayed', () => {
        const outer = element('<div><p>text</p></div>');
        const inner = outer.firstElementChild as HTMLElement;

        expect(is_visible(inner)).toBe(true);
        outer.style.display = 'none';
        expect(is_visible(inner)).toBe(false);
        expect(is_visible(document.createElement('p'))).toBe(false);
    });
});

describe('show and hide', () => {
    it('brings back the display the element had', () => {
        const el = element('<span style="display: inline-block">x</span>');

        hide(el);
        expect(el.style.display).toBe('none');
        show(el);
        expect(el.style.display).toBe('inline-block');
    });

    it('shows an element the stylesheet hides with its default display', () => {
        const el = element('<div class="hidden-by-css">x</div>');

        show(el);

        expect(el.style.display).toBe('block');
        expect(is_visible(el)).toBe(true);
    });

    it('toggles what is visible now, or to the given state', () => {
        const el = element('<div>x</div>');

        toggle(el);
        expect(is_visible(el)).toBe(false);
        toggle(el);
        expect(is_visible(el)).toBe(true);
        toggle(el, true);
        expect(is_visible(el)).toBe(true);
    });
});

describe('effects', () => {
    it('end shown or hidden at once when motion is reduced', async () => {
        const el = element('<div style="display: none">x</div>');

        await fade_in(el);
        expect(is_visible(el)).toBe(true);
        await fade_out(el);
        expect(is_visible(el)).toBe(false);
    });

    it('run with the Web Animations API otherwise', async () => {
        reduce_motion(false);
        const el = element('<div>x</div>');
        const animation = fake_animation();
        const animate = vi.spyOn(el, 'animate').mockReturnValue(animation);

        const done = slide_up(el, 50);
        expect(animate).toHaveBeenCalledWith(expect.any(Array), {
            duration: 50,
            easing: 'ease-in-out',
        });
        expect(is_visible(el)).toBe(true);
        animation.dispatchEvent(new Event('finish'));
        await done;

        expect(is_visible(el)).toBe(false);
    });

    it('jump to the end of a running effect when another starts', async () => {
        reduce_motion(false);
        const el = element('<div>x</div>');
        const animation = fake_animation();
        vi.spyOn(el, 'animate').mockReturnValue(animation);

        const hiding = fade_out(el);
        show(el);
        await hiding;

        expect(animation.cancel).toHaveBeenCalledOnce();
        expect(is_visible(el)).toBe(true);
    });
});
