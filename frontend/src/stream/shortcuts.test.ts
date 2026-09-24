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

import { init_shortcuts, kshortcuts } from './shortcuts';
import { stream_state } from './state';

function press(key: string, init: KeyboardEventInit = {}): KeyboardEvent {
    const event = new KeyboardEvent('keypress', { key, cancelable: true, ...init });
    kshortcuts(event);
    return event;
}

function highlighted(): string[] {
    return stream_state.articles
        .filter((a) => a.classList.contains('entry-highlight'))
        .map((a) => a.id);
}

beforeEach(() => {
    document.body.innerHTML = `
        <section id="stream">
          <article id="entry-1"><a href="#1">one</a></article>
          <article id="entry-2"><a href="#2">two</a></article>
          <nav><a class="next" href="?start=2">older</a></nav>
        </section>
        <input type="search" name="s">`;
    stream_state.articles = Array.from(document.querySelectorAll('article'));
    stream_state.nav_next = Array.from(document.querySelectorAll('nav a.next'));
    stream_state.current_article = -1;
    Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
    document.body.innerHTML = '';
});

describe('kshortcuts', () => {
    it('moves between entries with j and k', () => {
        const j = press('j');
        expect(highlighted()).toEqual(['entry-1']);
        expect(j.defaultPrevented).toBe(true);

        press('j');
        expect(highlighted()).toEqual(['entry-2']);

        press('k');
        expect(highlighted()).toEqual(['entry-1']);
    });

    it('clicks "next" when j moves past the last entry', () => {
        const next = vi.fn((e: Event) => e.preventDefault());
        stream_state.nav_next[0]?.addEventListener('click', next);
        stream_state.current_article = 1;

        press('j');

        expect(next).toHaveBeenCalledOnce();
    });

    it('leaves other keys and keys with modifiers alone', () => {
        const x = press('x');
        const ctrl_j = press('j', { ctrlKey: true });
        const shifted = press('J');

        expect(highlighted()).toEqual([]);
        expect(
            x.defaultPrevented || ctrl_j.defaultPrevented || shifted.defaultPrevented,
        ).toBe(false);
    });

    it('leaves a key typed in any field to the field', () => {
        document.body.insertAdjacentHTML(
            'beforeend',
            `<form><input name="username"><input type="password" name="password">
             <textarea></textarea><select><option>j</option></select></form>
             <div contenteditable="true"><p>text</p></div>`,
        );
        init_shortcuts();
        const fields = document.querySelectorAll<HTMLElement>(
            'input, textarea, select, [contenteditable] p',
        );

        for (const field of fields) {
            for (const key of ['j', 'k', 'a', 'f', 'h']) {
                const event = new KeyboardEvent('keypress', {
                    key,
                    bubbles: true,
                    cancelable: true,
                });
                field.dispatchEvent(event);
                expect(event.defaultPrevented, `${key} in ${field.tagName}`).toBe(
                    false,
                );
            }
        }
        expect(highlighted()).toEqual([]);

        const outside = new KeyboardEvent('keypress', {
            key: 'j',
            bubbles: true,
            cancelable: true,
        });
        document.body.dispatchEvent(outside);
        expect(highlighted()).toEqual(['entry-1']);
        expect(outside.defaultPrevented).toBe(true);
        document.removeEventListener('keypress', kshortcuts);
    });
});
