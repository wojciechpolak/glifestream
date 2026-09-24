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
import StarterKit from '@tiptap/starter-kit';

declare module '@tiptap/core' {
    interface Commands<ReturnType> {
        video: {
            /** Inserts a player that shows `src` in an iframe. */
            setVideo: (src: string) => ReturnType;
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

/** A video player, an <iframe>, as Quill's video button inserted. */
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

    addCommands() {
        return {
            setVideo:
                (src) =>
                ({ commands }) =>
                    is_web_url(src) &&
                    commands.insertContent({ type: this.name, attrs: { src } }),
        };
    },
});

export const extensions: Extensions = [
    StarterKit.configure({
        paragraph: false,
        // A pasted or typed address stays text, as Quill kept it: the
        // server turns a bare video, map or picture address into its player
        // or thumbnail. The toolbar's link button makes a link.
        link: { openOnClick: false, autolink: false, shouldAutoLink: () => false },
    }),
    Line,
    Align.configure({ types: ['heading', 'paragraph'], alignments: ALIGNMENTS }),
    // Inline, as Quill kept pictures within a line, and with data: URLs,
    // which Quill's image button inserted.
    Image.configure({ inline: true, allowBase64: true }),
    Video,
];
