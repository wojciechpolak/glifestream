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

import {
    PREVIEW_DELAY_MS,
    clear_preview,
    preview_article,
    refresh_preview,
    schedule_preview,
} from './preview';

const fetch_mock = vi.fn<typeof fetch>();

function article(text: string): Response {
    return new Response(
        `<article class="hentry"><div class="entry-content">${text}</div></article>`,
    );
}

/** The form a request sent. */
function sent(init: RequestInit | undefined): string {
    return init?.body instanceof URLSearchParams ? init.body.toString() : '';
}

/** A response that comes when the test says. */
function deferred(): { promise: Promise<Response>; resolve: (r: Response) => void } {
    const answer: { resolve: (r: Response) => void } = { resolve: () => undefined };
    const promise = new Promise<Response>((r) => {
        answer.resolve = r;
    });
    return { promise, resolve: (r) => answer.resolve(r) };
}

beforeEach(() => {
    document.body.innerHTML =
        '<main id="stream"><aside id="share"></aside><article class="hentry">old</article></main>';
    vi.stubGlobal('fetch', fetch_mock);
});

afterEach(() => {
    clear_preview();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    fetch_mock.mockReset();
});

describe('the live preview', () => {
    it('shows the article under the composer, where the post will be', async () => {
        fetch_mock.mockResolvedValueOnce(article('Hello'));

        await refresh_preview({ content: 'Hello' });

        const shown = preview_article();
        expect(shown?.previousElementSibling?.id).toBe('share');
        expect(shown?.querySelector('.entry-preview-label')?.textContent).toBe(
            'Preview',
        );
        expect(shown?.querySelector('.entry-content')?.textContent).toBe('Hello');
        const [url, init] = fetch_mock.mock.calls[0] ?? [];
        expect(url).toMatch(/\/api\/preview$/);
        expect(sent(init)).toBe('content=Hello');
    });

    it('asks once the composer is still, for what it holds then', async () => {
        vi.useFakeTimers();
        fetch_mock.mockResolvedValue(article('ab'));
        let content = 'a';

        schedule_preview(() => ({ content }));
        content = 'ab';
        schedule_preview(() => ({ content }));
        vi.advanceTimersByTime(PREVIEW_DELAY_MS - 1);
        expect(fetch_mock).not.toHaveBeenCalled();
        vi.advanceTimersByTime(1);

        expect(fetch_mock).toHaveBeenCalledTimes(1);
        expect(sent(fetch_mock.mock.calls[0]?.[1])).toBe('content=ab');
    });

    it('drops the answer to an older request', async () => {
        const first_answer = deferred();
        fetch_mock
            .mockReturnValueOnce(first_answer.promise)
            .mockResolvedValueOnce(article('second'));

        const first = refresh_preview({ content: 'first' });
        await refresh_preview({ content: 'second' });
        first_answer.resolve(article('first'));
        await first;

        expect(preview_article()?.querySelector('.entry-content')?.textContent).toBe(
            'second',
        );
    });

    it('goes away with nothing to show, or when it fails', async () => {
        fetch_mock.mockResolvedValueOnce(article('x'));
        await refresh_preview({ content: 'x' });

        await refresh_preview(null);
        expect(preview_article()).toBeNull();
        expect(fetch_mock).toHaveBeenCalledTimes(1);

        fetch_mock
            .mockResolvedValueOnce(article('y'))
            .mockResolvedValueOnce(new Response('', { status: 500 }));
        await refresh_preview({ content: 'y' });
        await refresh_preview({ content: 'z' });
        expect(preview_article()).toBeNull();
        expect(document.querySelectorAll('#stream > article')).toHaveLength(1);
    });
});
