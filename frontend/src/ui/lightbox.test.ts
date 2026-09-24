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

type Listener = (event: Record<string, unknown>) => void;

interface FakeSwipe {
    options: { dataSource: { src: string; w: number; h: number }[]; index: number };
    listeners: Record<string, Listener>;
    init: ReturnType<typeof vi.fn>;
}

const opened: FakeSwipe[] = [];

vi.mock('photoswipe', () => ({
    default: class {
        listeners: Record<string, Listener> = {};
        init = vi.fn();
        options: FakeSwipe['options'];
        constructor(options: FakeSwipe['options']) {
            this.options = options;
            opened.push(this as unknown as FakeSwipe);
        }
        on(name: string, listener: Listener): void {
            this.listeners[name] = listener;
        }
    },
}));
vi.mock('photoswipe/style.css', () => ({}));

const { Lightbox } = await import('./lightbox');

function thumbnails(...hrefs: string[]): string {
    const links = hrefs.map((href) => `<a href="${href}"><img src="data:,"></a>`);
    return `<div class="thumbnails">${links.join('')}</div>`;
}

beforeEach(() => {
    opened.length = 0;
    document.body.innerHTML = `
        <article id="entry-1">${thumbnails('/a.jpg', '/b.png', '/page.html')}</article>
        <article id="entry-2">${thumbnails('/c.jpg')}</article>`;
    Lightbox.scan();
});

afterEach(() => {
    document.body.innerHTML = '';
});

function click(href: string): MouseEvent {
    const event = new MouseEvent('click', { bubbles: true, cancelable: true });
    document.querySelector(`a[href="${href}"]`)?.dispatchEvent(event);
    return event;
}

describe('Lightbox', () => {
    it('opens the pictures of the entry, at the one clicked', () => {
        expect(click('/b.png').defaultPrevented).toBe(true);

        const [swipe] = opened;
        const origin = window.location.origin;
        expect(swipe?.options.dataSource.map((s) => s.src)).toEqual([
            origin + '/a.jpg',
            origin + '/b.png',
            origin + '/page.html',
        ]);
        expect(swipe?.options.index).toBe(1);
        expect(swipe?.init).toHaveBeenCalledOnce();
    });

    it('opens a picture alone when its entry has no other', () => {
        click('/c.jpg');

        expect(opened[0]?.options.dataSource).toHaveLength(1);
    });

    it('follows a link to a page that is not a picture', () => {
        expect(click('/page.html').defaultPrevented).toBe(false);
        expect(opened).toHaveLength(0);
    });

    it('opens the full picture a service links to', () => {
        document.body.innerHTML = `<article id="entry-3">${thumbnails(
            'https://www.instagram.com/p/Abc-1/',
        )}</article>`;
        Lightbox.scan();

        click('https://www.instagram.com/p/Abc-1/');

        expect(opened[0]?.options.dataSource[0]?.src).toBe(
            'https://instagram.com/p/Abc-1/media/?size=l',
        );
    });

    it.each([
        'http://twitpic.com/abc12',
        'http://yfrog.com/abc12',
        'http://instagr.am/p/Abc-1/',
        'http://m.friendfeed-media.com/0123abcd',
    ])('follows a link to %s, a picture service that is gone', (href) => {
        document.body.innerHTML = `<article id="entry-4">${thumbnails(href)}</article>`;
        Lightbox.scan();

        expect(click(href).defaultPrevented).toBe(false);
        expect(opened).toHaveLength(0);
    });

    it('gives a slide the size of its picture once it loads', () => {
        click('/a.jpg');
        const img = new Image();
        Object.defineProperties(img, {
            complete: { value: true },
            naturalWidth: { value: 1600 },
            naturalHeight: { value: 900 },
        });
        const slide = {
            width: 10,
            height: 10,
            content: { element: img },
            resize: vi.fn(),
        };

        opened[0]?.listeners['loadComplete']?.({ slide, isError: false });

        expect([slide.width, slide.height]).toEqual([1600, 900]);
        expect(slide.content).toMatchObject({ width: 1600, height: 900 });
        expect(slide.resize).toHaveBeenCalledOnce();
    });
});
