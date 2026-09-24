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

import { init_stream } from './init';
import { audio_embeds } from './media';
import { DEFAULT_SHARING_SITES, share_state } from './share';
import { stream_state } from './state';

const fetch_mock = vi.fn<typeof fetch>();

function stream_page(): void {
    document.body.innerHTML = `
        <aside id="sidebar">
          <a id="sidebar-toggle"><i class="fa-chevron-down"></i></a>
          <form name="searchform"><input name="s" value=""></form>
        </aside>
        <section id="stream">
          <article id="entry-1"><span class="play-audio" id="audio-1"></span></article>
          <article id="entry-2"></article>
          <nav><a class="next" href="/?start=2">older</a></nav>
        </section>`;
}

beforeEach(() => {
    vi.stubGlobal('fetch', fetch_mock);
    fetch_mock.mockReturnValue(new Promise(() => {}));
    stream_page();
});

afterEach(() => {
    vi.unstubAllGlobals();
    fetch_mock.mockReset();
    delete window.continuous_reading;
    delete window.social_sharing_sites;
    delete window.audio_embeds;
    delete audio_embeds['mine'];
    stream_state.continuous_reading = 300;
    document.body.innerHTML = '';
});

describe('init_stream', () => {
    it('collects the entries and the next links of the stream', () => {
        init_stream();

        expect(stream_state.articles.map((a) => a.id)).toEqual(['entry-1', 'entry-2']);
        expect(stream_state.nav_next).toEqual([document.querySelector('nav a.next')]);
        expect(document.getElementById('audio-1')?.title).toBe('Click and Listen');
    });

    it('loads the next page in place while reading continuously', () => {
        init_stream();

        document.querySelector<HTMLElement>('nav a.next')?.click();

        expect(fetch_mock.mock.calls[0]?.[0]).toMatch(/\?start=2&format=html-pure$/);
    });

    it('takes the settings of user-scripts.js', () => {
        const sites = [{ name: 'Mine', href: 'https://example.org/?u={URL}' }];
        window.continuous_reading = '0';
        window.social_sharing_sites = sites;
        window.audio_embeds = { mine: '<audio src="{ID}"></audio>' };

        init_stream();

        expect(stream_state.continuous_reading).toBe(0);
        expect(share_state.sites).toBe(sites);
        expect(audio_embeds['mine']).toBe('<audio src="{ID}"></audio>');
    });

    it('offers the default sharing sites', () => {
        init_stream();

        expect(share_state.sites).toBe(DEFAULT_SHARING_SITES);
    });

    it('expands and collapses the sidebar', () => {
        init_stream();

        document.getElementById('sidebar-toggle')?.click();

        expect(document.getElementById('sidebar')?.classList.contains('expanded')).toBe(
            true,
        );
        expect(document.querySelector('#sidebar-toggle i')?.className).toBe(
            'fa-chevron-up',
        );
    });

    it('does not search for nothing', () => {
        init_stream();
        const form = document.querySelector('form') as HTMLFormElement;
        const submit = new SubmitEvent('submit', { cancelable: true });

        form.dispatchEvent(submit);

        expect(submit.defaultPrevented).toBe(true);
    });

    it('sets up a page without a stream', () => {
        document.body.innerHTML = '<article id="entry-9"></article>';

        init_stream();

        expect(stream_state.articles.map((a) => a.id)).toEqual(['entry-9']);
        expect(stream_state.nav_next).toEqual([]);
    });
});
