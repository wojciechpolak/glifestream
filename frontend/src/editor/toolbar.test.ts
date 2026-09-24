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

import { video_embed_url } from './toolbar';

describe('video_embed_url', () => {
    it('turns a YouTube page into its player', () => {
        expect(video_embed_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ')).toBe(
            'https://www.youtube.com/embed/dQw4w9WgXcQ?showinfo=0',
        );
        expect(video_embed_url('youtu.be/dQw4w9WgXcQ')).toBe(
            'https://www.youtube.com/embed/dQw4w9WgXcQ?showinfo=0',
        );
    });

    it('turns a Vimeo page into its player', () => {
        expect(video_embed_url('http://vimeo.com/12345')).toBe(
            'http://player.vimeo.com/video/12345/',
        );
    });

    it('keeps any other address', () => {
        expect(video_embed_url('https://example.test/embed/1')).toBe(
            'https://example.test/embed/1',
        );
    });
});
