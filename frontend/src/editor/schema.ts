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

// What the composer's editor can hold. It also reads the HTML that Quill,
// the editor before it, wrote into entries, so that editing one of them
// keeps its lines, alignment and videos.

import { Node, mergeAttributes, type Extensions } from '@tiptap/core';
import Image from '@tiptap/extension-image';
import Paragraph from '@tiptap/extension-paragraph';
import TextAlign from '@tiptap/extension-text-align';
import type { DOMOutputSpec, Node as PmNode } from '@tiptap/pm/model';
import { NodeSelection, Plugin, PluginKey } from '@tiptap/pm/state';
import StarterKit from '@tiptap/starter-kit';

import {
    type Provider,
    type VideoRef,
    video_link,
    video_of,
    video_thumbnail,
} from './video';

/** A music card, as the composer's "Music track" fields describe it. */
export interface MusicTrack {
    artist: string;
    title: string;
    /** The address of the YouTube video that plays it, or ''. */
    youtube: string;
    /** The address of its cover, or ''. */
    cover: string;
}

declare module '@tiptap/core' {
    interface Commands<ReturnType> {
        musicCard: {
            /**
             * Makes the post's card show `track`: the card it has, or a new
             * one at its end; null takes the card away.
             */
            setMusicCard: (track: MusicTrack | null) => ReturnType;
        };
        player: {
            /**
             * Shows the video at `address` in a player: in the selected
             * player, or in a new one. Fails for an address of no video.
             */
            setPlayer: (address: string) => ReturnType;
        };
    }
}

const ALIGNMENTS = ['left', 'center', 'right', 'justify'];

/** Lines are <div>s, as in the entries the editor has always written. */
const Line = Paragraph.extend({
    parseHTML() {
        return [{ tag: 'div' }, { tag: 'p' }];
    },
    renderHTML({ HTMLAttributes }) {
        return ['div', mergeAttributes(this.options.HTMLAttributes, HTMLAttributes), 0];
    },
});

/** The alignment of a line: its style, or Quill's ql-align-* class. */
function line_alignment(element: HTMLElement): string | null {
    const quill = /\bql-align-(\w+)\b/.exec(element.className);
    const alignment = quill ? quill[1] : element.style.textAlign;
    return alignment && ALIGNMENTS.includes(alignment) ? alignment : null;
}

const Align = TextAlign.extend({
    addGlobalAttributes() {
        return [
            {
                types: this.options.types,
                attributes: {
                    textAlign: {
                        default: null,
                        parseHTML: line_alignment,
                        renderHTML: (attributes) =>
                            attributes['textAlign']
                                ? { style: `text-align: ${attributes['textAlign']}` }
                                : {},
                    },
                },
            },
        ];
    },
});

/** Whether a player address is one the editor keeps. */
function is_web_url(url: string | null): boolean {
    return url !== null && /^https?:\/\//i.test(url);
}

const PLAYER_ID = /^(youtube|vimeo)-([\w-]+)$/;
const ALT: Record<Provider, string> = {
    youtube: 'YouTube Video',
    vimeo: 'Vimeo Video',
};

/** The attributes of a stored play-video block, or false for another. */
function read_player(element: HTMLElement): Record<string, string> | false {
    const ident = PLAYER_ID.exec(
        element.getAttribute('data-id') ?? element.getAttribute('id') ?? '',
    );
    if (!ident?.[1] || !ident[2]) {
        return false;
    }
    const img = element.querySelector('img');
    return {
        provider: ident[1],
        videoId: ident[2],
        src: img?.getAttribute('src') ?? '',
        alt: img?.getAttribute('alt') ?? '',
    };
}

function player_attrs(video: VideoRef): Record<string, string> {
    return {
        provider: video.provider,
        videoId: video.id,
        src: video_thumbnail(video),
        alt: '',
    };
}

function video_ref(node: PmNode): VideoRef {
    return {
        provider: node.attrs['provider'] as Provider,
        id: node.attrs['videoId'] as string,
    };
}

/** The address of the video of a selected player, or null. */
export function selected_video(selection: unknown): string | null {
    if (selection instanceof NodeSelection && selection.node.type.name === 'player') {
        return video_link(video_ref(selection.node));
    }
    return null;
}

/**
 * A video as a post shows it: its thumbnail, which the stream turns into
 * the video. It is saved in the markup of the server's players, which
 * gives it a thumbnail of its own (glifestream/filters/players.py).
 */
const Player = Node.create({
    name: 'player',
    group: 'block',
    atom: true,
    draggable: true,
    selectable: true,

    addAttributes() {
        return {
            provider: { default: 'youtube' },
            videoId: { default: null },
            src: { default: '' },
            alt: { default: '' },
        };
    },

    parseHTML() {
        // Before a line, which a <div> would otherwise be.
        return ['div', 'span'].map((tag) => ({
            tag: `${tag}.play-video`,
            priority: 100,
            getAttrs: read_player,
        }));
    },

    renderHTML({ node }) {
        const video = video_ref(node);
        const alt = (node.attrs['alt'] as string) || ALT[video.provider];
        return [
            'div',
            { 'data-id': `${video.provider}-${video.id}`, class: 'play-video' },
            [
                'a',
                { href: video_link(video), rel: 'nofollow' },
                [
                    'img',
                    {
                        src: node.attrs['src'] as string,
                        width: '320',
                        height: '180',
                        alt,
                    },
                ],
            ],
            ['div', { class: 'playbutton' }],
        ];
    },

    addNodeView() {
        // The stream's own markup, which the theme draws: the frame of the
        // thumbnail and the play button, as the post will show them.
        return ({ node }) => {
            const video = video_ref(node);
            const dom = document.createElement('div');
            dom.className = 'editor-player';
            dom.contentEditable = 'false';
            dom.dataset['provider'] = video.provider;
            const block = document.createElement('div');
            block.className = 'play-video';
            const src = node.attrs['src'] as string;
            if (src) {
                const img = document.createElement('img');
                img.src = src;
                img.width = 320;
                img.height = 180;
                img.alt = (node.attrs['alt'] as string) || ALT[video.provider];
                block.append(img);
            } else {
                const name = document.createElement('span');
                name.className = 'editor-player-name';
                name.textContent = video.provider === 'youtube' ? 'YouTube' : 'Vimeo';
                block.append(name);
            }
            const play = document.createElement('div');
            play.className = 'playbutton';
            play.setAttribute('aria-hidden', 'true');
            block.append(play);
            const link = document.createElement('span');
            link.className = 'editor-player-link';
            link.textContent = video_link(video);
            dom.append(block, link);
            return { dom };
        };
    },

    addCommands() {
        return {
            setPlayer:
                (address) =>
                ({ state, tr, dispatch }) => {
                    const video = video_of(address);
                    if (!video) {
                        return false;
                    }
                    const attrs = player_attrs(video);
                    const { selection } = state;
                    if (dispatch) {
                        if (
                            selection instanceof NodeSelection &&
                            selection.node.type.name === this.name
                        ) {
                            tr.setNodeMarkup(selection.from, undefined, attrs);
                        } else {
                            tr.replaceSelectionWith(this.type.create(attrs));
                        }
                    }
                    return true;
                },
        };
    },

    addProseMirrorPlugins() {
        const type = this.type;
        return [
            new Plugin({
                key: new PluginKey('player-paste'),
                props: {
                    // A video address pasted on its own shows as its player,
                    // as the post will; one within other text stays text.
                    handlePaste: (view, event, slice) => {
                        const text = (
                            event.clipboardData?.getData('text/plain') ??
                            slice.content.textBetween(0, slice.content.size, ' ')
                        ).trim();
                        const video = /\s/.test(text) ? null : video_of(text);
                        if (!video) {
                            return false;
                        }
                        view.dispatch(
                            view.state.tr
                                .replaceSelectionWith(type.create(player_attrs(video)))
                                .scrollIntoView(),
                        );
                        return true;
                    },
                },
            }),
        ];
    },
});

// The services a card links to a search on (glifestream/filters/music.py).
const LISTEN_ON = [
    'Spotify',
    'Apple Music',
    'YouTube Music',
    'Deezer',
    'Tidal',
    'Bandcamp',
];

/** The track a stored card shows, or false for another element. */
function read_card(element: HTMLElement): MusicTrack | false {
    const text = (cls: string): string =>
        element.querySelector('.' + cls)?.textContent?.trim() ?? '';
    const video = /^youtube-([\w-]+)$/.exec(
        element.querySelector('[data-id]')?.getAttribute('data-id') ?? '',
    );
    return {
        artist: text('music-artist'),
        title: text('music-title'),
        youtube: video?.[1] ? video_link({ provider: 'youtube', id: video[1] }) : '',
        cover: element.querySelector('img')?.getAttribute('src') ?? '',
    };
}

function track_of(node: PmNode): MusicTrack {
    const attrs = node.attrs as MusicTrack;
    return {
        artist: attrs.artist,
        title: attrs.title,
        youtube: attrs.youtube,
        cover: attrs.cover,
    };
}

function youtube_of(track: MusicTrack): VideoRef | null {
    const video = video_of(track.youtube);
    return video?.provider === 'youtube' ? video : null;
}

/** The card as the stream shows it, which the theme draws. */
function card_view(track: MusicTrack): HTMLElement {
    const card = document.createElement('div');
    card.className = 'music-card';
    const video = youtube_of(track);
    const src = track.cover || (video ? video_thumbnail(video) : '');
    const img = document.createElement('img');
    img.src = src;
    img.alt = '';
    if (video) {
        const block = document.createElement('div');
        block.className = 'play-video';
        const play = document.createElement('div');
        play.className = 'playbutton';
        block.append(img, play);
        card.append(block);
    } else if (src) {
        const cover = document.createElement('span');
        cover.className = 'music-cover';
        cover.append(img);
        card.append(cover);
    }
    const line = document.createElement('p');
    line.className = 'music-track';
    const title = document.createElement('span');
    title.className = 'music-title';
    title.textContent = track.title;
    const artist = document.createElement('span');
    artist.className = 'music-artist';
    artist.textContent = track.artist;
    line.append(title, ' ', artist);
    const links = document.createElement('p');
    links.className = 'music-links';
    links.textContent = LISTEN_ON.join(' · ');
    card.append(line, links);
    return card;
}

/**
 * A post's music card. The "Music track" fields edit it; it is saved as
 * the track it shows, and the server makes the card again from that, with
 * its saved cover and its links (glifestream/filters/music.py).
 */
const MusicCard = Node.create({
    name: 'musicCard',
    group: 'block',
    atom: true,
    draggable: true,
    selectable: true,

    addAttributes() {
        return {
            artist: { default: '' },
            title: { default: '' },
            youtube: { default: '' },
            cover: { default: '' },
        };
    },

    parseHTML() {
        return [{ tag: 'div.music-card', priority: 110, getAttrs: read_card }];
    },

    renderHTML({ node }) {
        const track = track_of(node);
        const video = youtube_of(track);
        // A size of its own the server reads from the cover once it has it.
        const img = ['img', { src: track.cover, width: '160', height: '160', alt: '' }];
        const parts: DOMOutputSpec[] = [];
        if (video) {
            parts.push([
                'div',
                { 'data-id': `youtube-${video.id}`, class: 'play-video' },
                [
                    'a',
                    { href: video_link(video), rel: 'nofollow' },
                    track.cover ? img : 'YouTube',
                ],
                ['div', { class: 'playbutton' }],
            ]);
        } else if (track.cover) {
            parts.push(['span', { class: 'music-cover' }, img]);
        }
        parts.push(
            [
                'p',
                { class: 'music-track' },
                ['span', { class: 'music-title' }, track.title],
                ' ',
                ['span', { class: 'music-artist' }, track.artist],
            ],
            ['p', { class: 'music-links' }],
        );
        return ['div', { class: 'music-card' }, ...parts];
    },

    addNodeView() {
        return ({ node }) => {
            const dom = document.createElement('div');
            dom.className = 'editor-music-card';
            dom.contentEditable = 'false';
            dom.append(card_view(track_of(node)));
            return { dom };
        };
    },

    addCommands() {
        return {
            setMusicCard:
                (track) =>
                ({ state, tr, dispatch }) => {
                    let at = -1;
                    state.doc.descendants((node, pos) => {
                        if (at === -1 && node.type.name === this.name) {
                            at = pos;
                        }
                        return at === -1;
                    });
                    if (dispatch) {
                        if (track === null) {
                            if (at !== -1) {
                                tr.delete(at, at + 1);
                            }
                        } else if (at !== -1) {
                            tr.setNodeMarkup(at, undefined, { ...track });
                        } else {
                            tr.insert(
                                state.doc.content.size,
                                this.type.create({ ...track }),
                            );
                        }
                    }
                    return track !== null || at !== -1;
                },
        };
    },
});

/** The track of the post's music card, or null when it has none. */
export function music_card_of(doc: PmNode): MusicTrack | null {
    let track: MusicTrack | null = null;
    doc.descendants((node) => {
        if (track === null && node.type.name === 'musicCard') {
            track = track_of(node);
        }
        return track === null;
    });
    return track;
}

/** A video player, an <iframe>, as Quill's video button inserted, kept
 * only to read the entries it wrote. */
const Video = Node.create({
    name: 'video',
    group: 'block',
    atom: true,
    draggable: true,

    addAttributes() {
        return { src: { default: null } };
    },

    parseHTML() {
        return [
            {
                tag: 'iframe[src]',
                getAttrs: (element) =>
                    is_web_url(element.getAttribute('src')) ? null : false,
            },
        ];
    },

    renderHTML({ HTMLAttributes }) {
        return [
            'iframe',
            mergeAttributes(
                { frameborder: '0', allowfullscreen: 'true' },
                HTMLAttributes,
            ),
        ];
    },
});

export const extensions: Extensions = [
    StarterKit.configure({
        paragraph: false,
        // A typed address stays text, as Quill kept it: the server turns a
        // bare video, map or picture address into its player or thumbnail.
        // A video address pasted on its own is a player at once (Player).
        // The toolbar's link button makes a link.
        link: { openOnClick: false, autolink: false, shouldAutoLink: () => false },
    }),
    Line,
    Align.configure({ types: ['heading', 'paragraph'], alignments: ALIGNMENTS }),
    // Inline, as Quill kept pictures within a line, and with data: URLs,
    // which Quill's image button inserted.
    Image.configure({ inline: true, allowBase64: true }),
    Video,
    Player,
    MusicCard,
];
