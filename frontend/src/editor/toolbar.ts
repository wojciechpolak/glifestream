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

// The formatting buttons above the composer's editor. Their icons are Font
// Awesome's, which every theme's stylesheet carries.

import type { ChainedCommands, Editor } from '@tiptap/core';

type Gettext = (msg: string) => string;

interface Tool {
    /** The button's name, translated. */
    label: string;
    /** The Font Awesome icon, or text when it starts with no fa-. */
    icon: string;
    run: (editor: Editor, gettext: Gettext) => void;
    /** Whether the button shows as pressed where the selection is. */
    active?: (editor: Editor) => boolean;
}

function command(apply: (chain: ChainedCommands) => ChainedCommands): Tool['run'] {
    return (editor) => {
        apply(editor.chain().focus()).run();
    };
}

/**
 * The address of the player for a video's page on YouTube or Vimeo, as
 * Quill's video button made it; any other address as it is.
 */
export function video_embed_url(url: string): string {
    const youtube =
        /^(?:(https?):\/\/)?(?:(?:www|m)\.)?youtube\.com\/watch.*v=([\w-]+)/.exec(
            url,
        ) || /^(?:(https?):\/\/)?(?:(?:www|m)\.)?youtu\.be\/([\w-]+)/.exec(url);
    if (youtube) {
        return `${youtube[1] || 'https'}://www.youtube.com/embed/${youtube[2]}?showinfo=0`;
    }
    const vimeo = /^(?:(https?):\/\/)?(?:www\.)?vimeo\.com\/(\d+)/.exec(url);
    if (vimeo) {
        return `${vimeo[1] || 'https'}://player.vimeo.com/video/${vimeo[2]}/`;
    }
    return url;
}

function edit_link(editor: Editor, gettext: Gettext): void {
    const current = editor.getAttributes('link')['href'] as string | undefined;
    const href = prompt(gettext('Link address:'), current || 'https://');
    if (href === null) {
        return;
    }
    const chain = editor.chain().focus().extendMarkRange('link');
    if (href.trim() === '' || href.trim() === 'https://') {
        chain.unsetLink().run();
    } else {
        chain.setLink({ href: href.trim() }).run();
    }
}

/** Picks a picture and puts it in the text as a data: URL, as Quill did. */
function insert_image(editor: Editor): void {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.addEventListener('change', () => {
        const file = input.files?.[0];
        if (!file) {
            return;
        }
        const reader = new FileReader();
        reader.addEventListener('load', () => {
            // readAsDataURL gives a string.
            const src = reader.result as string;
            editor.chain().focus().setImage({ src }).run();
        });
        reader.readAsDataURL(file);
    });
    input.click();
}

function insert_video(editor: Editor, gettext: Gettext): void {
    const url = prompt(gettext('Video address:'), 'https://');
    if (url && url.trim() !== 'https://') {
        editor.chain().focus().setVideo(video_embed_url(url.trim())).run();
    }
}

function align(alignment: string, label: string, icon: string): Tool {
    return {
        label,
        icon,
        run: command((c) => c.setTextAlign(alignment)),
        active: (editor) => editor.isActive({ textAlign: alignment }),
    };
}

/** The buttons, in groups, named in the page's language. */
function tool_groups(gettext: Gettext): Tool[][] {
    return [
        [
            {
                label: gettext('Bold'),
                icon: 'fa-bold',
                run: command((c) => c.toggleBold()),
                active: (e) => e.isActive('bold'),
            },
            {
                label: gettext('Italic'),
                icon: 'fa-italic',
                run: command((c) => c.toggleItalic()),
                active: (e) => e.isActive('italic'),
            },
            {
                label: gettext('Underline'),
                icon: 'fa-underline',
                run: command((c) => c.toggleUnderline()),
                active: (e) => e.isActive('underline'),
            },
            {
                label: gettext('Strikethrough'),
                icon: 'fa-strikethrough',
                run: command((c) => c.toggleStrike()),
                active: (e) => e.isActive('strike'),
            },
        ],
        [
            {
                label: gettext('Heading 1'),
                icon: 'H1',
                run: command((c) => c.toggleHeading({ level: 1 })),
                active: (e) => e.isActive('heading', { level: 1 }),
            },
            {
                label: gettext('Heading 2'),
                icon: 'H2',
                run: command((c) => c.toggleHeading({ level: 2 })),
                active: (e) => e.isActive('heading', { level: 2 }),
            },
            {
                label: gettext('Quote'),
                icon: 'fa-quote-right',
                run: command((c) => c.toggleBlockquote()),
                active: (e) => e.isActive('blockquote'),
            },
            {
                label: gettext('Code block'),
                icon: 'fa-code',
                run: command((c) => c.toggleCodeBlock()),
                active: (e) => e.isActive('codeBlock'),
            },
        ],
        [
            {
                label: gettext('Numbered list'),
                icon: 'fa-list-ol',
                run: command((c) => c.toggleOrderedList()),
                active: (e) => e.isActive('orderedList'),
            },
            {
                label: gettext('Bullet list'),
                icon: 'fa-list-ul',
                run: command((c) => c.toggleBulletList()),
                active: (e) => e.isActive('bulletList'),
            },
        ],
        [
            align('left', gettext('Align left'), 'fa-align-left'),
            align('center', gettext('Align center'), 'fa-align-center'),
            align('right', gettext('Align right'), 'fa-align-right'),
            align('justify', gettext('Justify'), 'fa-align-justify'),
        ],
        [
            {
                label: gettext('Link'),
                icon: 'fa-link',
                run: edit_link,
                active: (e) => e.isActive('link'),
            },
            { label: gettext('Image'), icon: 'fa-image', run: insert_image },
            { label: gettext('Video'), icon: 'fa-film', run: insert_video },
        ],
        [
            {
                label: gettext('Clear formatting'),
                icon: 'fa-remove-format',
                run: command((c) => c.unsetAllMarks().clearNodes()),
            },
        ],
    ];
}

function button(editor: Editor, tool: Tool, gettext: Gettext): HTMLButtonElement {
    const el = document.createElement('button');
    el.type = 'button';
    el.title = tool.label;
    el.setAttribute('aria-label', el.title);
    if (tool.icon.startsWith('fa-')) {
        const icon = document.createElement('i');
        icon.className = 'fa-solid ' + tool.icon;
        icon.setAttribute('aria-hidden', 'true');
        el.append(icon);
    } else {
        el.textContent = tool.icon;
    }
    // Keeps the selection in the text while the button is pressed.
    el.addEventListener('mousedown', (event) => event.preventDefault());
    el.addEventListener('click', () => tool.run(editor, gettext));
    return el;
}

/** The toolbar of `editor`, whose buttons show what the selection has. */
export function build_toolbar(editor: Editor, gettext: Gettext): HTMLElement {
    const toolbar = document.createElement('div');
    toolbar.className = 'editor-toolbar';
    toolbar.setAttribute('role', 'toolbar');
    toolbar.setAttribute('aria-label', gettext('Formatting'));
    const toggles: [HTMLButtonElement, NonNullable<Tool['active']>][] = [];
    for (const tools of tool_groups(gettext)) {
        const group = document.createElement('span');
        group.className = 'editor-toolbar-group';
        for (const tool of tools) {
            const el = button(editor, tool, gettext);
            if (tool.active) {
                toggles.push([el, tool.active]);
            }
            group.append(el);
        }
        toolbar.append(group);
    }
    const refresh = (): void => {
        for (const [el, active] of toggles) {
            el.setAttribute('aria-pressed', String(active(editor)));
        }
    };
    editor.on('transaction', refresh);
    refresh();
    return toolbar;
}
