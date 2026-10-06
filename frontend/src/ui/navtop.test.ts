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

import { init_navtop } from './navtop';

/** The listeners the tested code added to the document, removed after each test. */
const added: [string, EventListenerOrEventListenerObject][] = [];
/** The listener the tested code gave the wide-screen media query. */
let on_media_change: ((query: { matches: boolean }) => void) | null = null;

function nav(): HTMLElement {
    return document.getElementById('navtop') as HTMLElement;
}

function toggle(): HTMLButtonElement {
    return document.getElementById('navtop-toggle') as HTMLButtonElement;
}

function click(target: Element): void {
    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

beforeEach(() => {
    const add = document.addEventListener.bind(document);
    vi.spyOn(document, 'addEventListener').mockImplementation(
        (type, listener, options) => {
            added.push([type, listener]);
            add(type, listener, options);
        },
    );
    vi.spyOn(window, 'matchMedia').mockReturnValue({
        matches: false,
        addEventListener: (_type: string, listener: typeof on_media_change) => {
            on_media_change = listener;
        },
    } as unknown as MediaQueryList);
    document.body.innerHTML = `
        <header id="head">
          <nav id="navtop">
            <button type="button" id="navtop-toggle" aria-expanded="false"></button>
            <div id="navtop-menu"><a href="#settings">Settings</a></div>
          </nav>
          <h1>The Stream</h1>
        </header>`;
    init_navtop();
});

afterEach(() => {
    for (const [type, listener] of added.splice(0)) {
        document.removeEventListener(type, listener);
    }
    on_media_change = null;
    vi.restoreAllMocks();
    document.body.innerHTML = '';
});

describe('init_navtop', () => {
    it('opens and closes the menu from its button', () => {
        click(toggle());
        expect(nav().classList.contains('open')).toBe(true);
        expect(toggle().getAttribute('aria-expanded')).toBe('true');

        click(toggle());
        expect(nav().classList.contains('open')).toBe(false);
        expect(toggle().getAttribute('aria-expanded')).toBe('false');
    });

    it('stays open on a click inside the menu', () => {
        click(toggle());
        click(document.querySelector('#navtop-menu') as HTMLElement);
        expect(nav().classList.contains('open')).toBe(true);
    });

    it('closes on a click elsewhere on the page', () => {
        click(toggle());
        click(document.querySelector('h1') as HTMLElement);
        expect(nav().classList.contains('open')).toBe(false);
        expect(toggle().getAttribute('aria-expanded')).toBe('false');
    });

    it('closes on Escape and gives the focus back to its button', () => {
        click(toggle());
        (document.querySelector('#navtop-menu a') as HTMLElement).focus();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
        expect(nav().classList.contains('open')).toBe(false);
        expect(document.activeElement).toBe(toggle());
    });

    it('closes when the screen becomes wide', () => {
        click(toggle());
        on_media_change?.({ matches: false });
        expect(nav().classList.contains('open')).toBe(true);
        on_media_change?.({ matches: true });
        expect(nav().classList.contains('open')).toBe(false);
    });

    it('does nothing on a page without the menu', () => {
        document.body.innerHTML = '<nav id="navtop"></nav>';
        expect(() => init_navtop()).not.toThrow();
    });
});
