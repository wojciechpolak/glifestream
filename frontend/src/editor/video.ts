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

// The videos a post can play: the addresses of YouTube and Vimeo, read as
// the server reads them (glifestream/filters/players.py).

export type Provider = 'youtube' | 'vimeo';

export interface VideoRef {
    provider: Provider;
    id: string;
}

const ID = /^[\w-]+$/;

/** Where an address of a host carries the video id: its path parts. */
type IdOf = (url: URL, parts: string[]) => string | null | undefined;

const VIDEO_PATHS = new Set(['shorts', 'live', 'embed']);

const youtube_path_id: IdOf = (url, parts) =>
    url.pathname.replace(/\/$/, '') === '/watch'
        ? url.searchParams.get('v')
        : VIDEO_PATHS.has(parts[0] ?? '')
          ? parts[1]
          : null;

// Host (without "www.") -> how it carries the video id, as on the server.
const YOUTUBE_ID: Record<string, IdOf> = {
    'youtube.com': youtube_path_id,
    'm.youtube.com': youtube_path_id,
    'music.youtube.com': youtube_path_id,
    'youtu.be': (_url, parts) => parts[0],
    'youtube-nocookie.com': (_url, parts) => (parts[0] === 'embed' ? parts[1] : null),
};

function youtube_id(url: URL): string | null {
    const id_of = YOUTUBE_ID[url.hostname.toLowerCase().replace(/^www\./, '')];
    const parts = url.pathname.split('/').filter((part) => part !== '');
    return id_of?.(url, parts) ?? null;
}

const VIMEO =
    /^https?:\/\/(?:www\.|player\.)?vimeo\.com\/(?:[^?#]*\/)?(\d+)\/?(?:[?#].*)?$/;

/** The video an address shows, or null when it shows none. */
export function video_of(address: string): VideoRef | null {
    const text = address.trim();
    const vimeo = VIMEO.exec(text);
    if (vimeo?.[1]) {
        return { provider: 'vimeo', id: vimeo[1] };
    }
    let url: URL;
    try {
        url = new URL(text);
    } catch {
        return null;
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
        return null;
    }
    const id = youtube_id(url);
    return id && ID.test(id) ? { provider: 'youtube', id } : null;
}

/** The page of a video. */
export function video_link(video: VideoRef): string {
    return video.provider === 'youtube'
        ? `https://www.youtube.com/watch?v=${video.id}`
        : `https://vimeo.com/${video.id}`;
}

/**
 * The provider's thumbnail of a video, to show until the post is saved
 * with one of its own; Vimeo needs a request for it, which the server makes.
 */
export function video_thumbnail(video: VideoRef): string {
    return video.provider === 'youtube'
        ? `https://i.ytimg.com/vi/${video.id}/mqdefault.jpg`
        : '';
}
