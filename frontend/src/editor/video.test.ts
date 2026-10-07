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

import { describe, expect, it } from 'vitest';

import { video_link, video_of, video_thumbnail } from './video';

describe('video_of', () => {
    it.each([
        ['https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1', 'dQw4w9WgXcQ'],
        [' https://youtu.be/dQw4w9WgXcQ ', 'dQw4w9WgXcQ'],
        ['https://m.youtube.com/shorts/abc-1', 'abc-1'],
        ['https://music.youtube.com/watch?v=abc', 'abc'],
        ['https://www.youtube-nocookie.com/embed/abc', 'abc'],
    ])('reads a YouTube address: %s', (address, id) => {
        expect(video_of(address)).toEqual({ provider: 'youtube', id });
    });

    it.each([
        'https://vimeo.com/42',
        'https://player.vimeo.com/video/42',
        'https://vimeo.com/channels/staffpicks/42?share=1',
    ])('reads a Vimeo address: %s', (address) => {
        expect(video_of(address)).toEqual({ provider: 'vimeo', id: '42' });
    });

    it.each(['https://example.test/watch?v=x', 'youtu.be/abc', 'javascript:x', 'text'])(
        'reads no video in %s',
        (address) => {
            expect(video_of(address)).toBeNull();
        },
    );

    it('gives the page and the preview of a video', () => {
        const yt = { provider: 'youtube', id: 'abc' } as const;
        expect(video_link(yt)).toBe('https://www.youtube.com/watch?v=abc');
        expect(video_thumbnail(yt)).toBe('https://i.ytimg.com/vi/abc/mqdefault.jpg');
        expect(video_link({ provider: 'vimeo', id: '42' })).toBe(
            'https://vimeo.com/42',
        );
        expect(video_thumbnail({ provider: 'vimeo', id: '42' })).toBe('');
    });
});
