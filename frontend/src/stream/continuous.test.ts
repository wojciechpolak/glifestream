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

import { load_entries } from './continuous';
import { stream_state } from './state';

const fetch_mock = vi.fn<typeof fetch>();

function page(stream: string, next: number | null): void {
    fetch_mock.mockResolvedValueOnce(Response.json({ stream, next }));
}

function next_link(): HTMLAnchorElement {
    return document.querySelector('nav a.next') as HTMLAnchorElement;
}

function stream_page(href: string): void {
    document.body.innerHTML = `
        <section id="stream">
          <article id="entry-1">one</article>
          <article id="entry-2">two</article>
          <nav><a class="next" href="${href}">older</a></nav>
        </section>`;
    stream_state.articles = Array.from(document.querySelectorAll('article'));
    stream_state.nav_next = [next_link()];
}

beforeEach(() => {
    vi.stubGlobal('fetch', fetch_mock);
    stream_state.continuous_reading = 300;
});

afterEach(() => {
    vi.unstubAllGlobals();
    fetch_mock.mockReset();
    document.body.innerHTML = '';
});

describe('load_entries', () => {
    it('appends the next page in place and points the link past it', async () => {
        stream_page('/?start=2');
        page('<article id="entry-3">three</article>', 3);

        expect(load_entries(next_link())).toBe(false);
        expect(document.getElementById('spinner')).not.toBeNull();
        await vi.waitFor(() => expect(stream_state.articles).toHaveLength(3));

        expect(fetch_mock.mock.calls[0]?.[0]).toMatch(/\/\?start=2&format=html-pure$/);
        expect(stream_state.articles.map((a) => a.id)).toEqual([
            'entry-1',
            'entry-2',
            'entry-3',
        ]);
        expect(next_link().href).toMatch(/\/\?start=3$/);
        expect(document.getElementById('spinner')).toBeNull();
    });

    it('advances a paged link too', async () => {
        stream_page('/favorites?page=2');
        page('<article id="entry-3">three</article>', 3);

        load_entries(next_link());
        await vi.waitFor(() => expect(stream_state.articles).toHaveLength(3));

        expect(fetch_mock.mock.calls[0]?.[0]).toMatch(/\?page=2&format=html-pure$/);
        expect(next_link().href).toMatch(/\/favorites\?page=3$/);
    });

    it('drops the link after the last page', async () => {
        stream_page('/?start=2');
        page('<article id="entry-3">three</article>', null);

        load_entries(next_link());
        await vi.waitFor(() => expect(stream_state.articles).toHaveLength(3));

        expect(next_link()).toBeNull();
    });

    it('ignores clicks while a page is on its way', () => {
        stream_page('/?start=2');
        fetch_mock.mockReturnValue(new Promise(() => {}));

        load_entries(next_link());
        expect(load_entries(next_link())).toBe(false);

        expect(fetch_mock).toHaveBeenCalledTimes(1);
    });

    it('follows the link once the page holds enough entries', () => {
        stream_page('#older');
        stream_state.continuous_reading = 2;

        expect(load_entries(next_link())).toBe(false);

        expect(fetch_mock).not.toHaveBeenCalled();
        expect(window.location.hash).toBe('#older');
    });
});
