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

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { Shareitbox, share_state, shareit_entry } from './share';

beforeEach(() => {
    share_state.sites = [
        {
            name: 'Mail',
            href: 'mailto:?subject={URL}&body={TITLE}',
            className: 'email',
        },
        { name: 'Custom', href: 'https://share.example/?u={URL}', icon: '/c.png' },
    ];
    window.history.replaceState(null, '', '/');
});

afterEach(() => {
    Shareitbox.close();
    document.body.innerHTML = '';
});

function entry(html: string): HTMLElement {
    document.body.innerHTML = `
        <article id="entry-5" class="${html.includes('private') ? 'private' : ''}">
          ${html}
          <div class="entry-meta"><a href="#" id="share-5" class="shareit">Share</a></div>
        </article>`;
    return document.getElementById('share-5') as HTMLElement;
}

function hrefs(): string[] {
    return Array.from(
        document.querySelectorAll<HTMLAnchorElement>('#shareitbox .item a'),
        (a) => a.getAttribute('href') as string,
    );
}

describe('shareit_entry', () => {
    it('shares the entry link and its title as plain text', () => {
        const link = entry(`
            <h2 class="entry-title"> A &amp; <b>B</b> </h2>
            <a rel="bookmark" href="/entry/5">permalink</a>`);

        expect(shareit_entry(link)).toBe(false);

        const url = encodeURIComponent('http://' + window.location.host + '/entry/5');
        expect(hrefs()).toEqual([
            'mailto:?subject=' + url + '&body=' + encodeURIComponent('A & B'),
            'https://share.example/?u=' + url,
        ]);
        expect(document.querySelector('#shareitbox .reshare')?.textContent).toBe(
            'Share or bookmark this entry',
        );
        expect(document.querySelector('#shareitbox img')?.getAttribute('src')).toBe(
            '/c.png',
        );
        expect(document.getElementById('overlay')).not.toBeNull();
    });

    it('shares the content, shortened, of an entry without a title', () => {
        const link = entry(`
            <div class="entry-content">${'word '.repeat(40)}</div>
            <a rel="bookmark" href="/entry/5">permalink</a>`);

        shareit_entry(link);

        const body = new URL(hrefs()[0] as string).searchParams.get('body') as string;
        expect(body).toHaveLength(140);
        expect(body.endsWith('...')).toBe(true);
    });
});

describe('Shareitbox', () => {
    it('closes on Escape and on the overlay', () => {
        Shareitbox.open({ id: '5', url: 'https://a.example/', title: 'A' });
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

        const box = document.getElementById('shareitbox') as HTMLElement;
        expect(box.style.display).toBe('none');
        expect(box.childElementCount).toBe(0);
        expect(document.getElementById('overlay')).toBeNull();

        Shareitbox.open({ id: '5', url: 'https://a.example/', title: 'A' });
        document.getElementById('overlay')?.click();
        expect(box.style.display).toBe('none');
    });

    it('offers resharing on the reader stream', () => {
        Shareitbox.open({ id: '5', reshareit: true });

        const reshare = document.getElementById('reshare-5');
        expect(reshare?.textContent).toBe('Reshare it at your stream');
        expect(reshare?.parentElement?.textContent).toBe(
            'Reshare it at your stream or elsewhere: ',
        );
    });
});
