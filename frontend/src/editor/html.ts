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

// The editor's HTML on its way in and out. Entries keep the markup Quill
// wrote, so what the editor saves looks the same: a list item holds its
// text rather than a line, an empty line is <div><br></div> and none ends
// the text, and a run of spaces stays as wide as it was typed.

function fragment(html: string): DocumentFragment {
    const template = document.createElement('template');
    template.innerHTML = html;
    return template.content;
}

function serialize(root: DocumentFragment): string {
    const container = document.createElement('div');
    container.append(root);
    return container.innerHTML;
}

/** Keeps a run of spaces from collapsing: a space, then no-break spaces. */
function keep_spaces(root: DocumentFragment): void {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.parentElement?.closest('pre, code')) {
            continue;
        }
        node.nodeValue = (node.nodeValue ?? '').replace(
            / {2,}/g,
            (run) => ' ' + ' '.repeat(run.length - 1),
        );
    }
}

/** The editor's HTML, as it is saved. */
export function saved_html(html: string): string {
    const root = fragment(html);
    for (const item of root.querySelectorAll('li')) {
        const line = item.firstElementChild;
        if (item.childNodes.length === 1 && line?.tagName === 'DIV') {
            const style = line.getAttribute('style');
            if (style) {
                item.setAttribute('style', style);
            }
            item.replaceChildren(...line.childNodes);
        }
    }
    // The editor keeps an empty line after a list or a player to type in.
    for (
        let last = root.lastElementChild;
        last?.tagName === 'DIV' && !last.hasChildNodes() && last.previousSibling;
        last = root.lastElementChild
    ) {
        last.remove();
    }
    for (const line of root.querySelectorAll('div, li')) {
        if (!line.hasChildNodes()) {
            line.append(document.createElement('br'));
        }
    }
    keep_spaces(root);
    return serialize(root);
}

/** An entry's HTML, as the editor reads it: an empty line loses its <br>. */
export function loadable_html(html: string): string {
    const root = fragment(html);
    for (const line of root.querySelectorAll('div, p, li')) {
        if (line.childNodes.length === 1 && line.firstChild?.nodeName === 'BR') {
            line.replaceChildren();
        }
    }
    return serialize(root);
}

/** Whether the HTML holds neither text, a picture nor a player. */
export function is_html_empty(value: string): boolean {
    return (
        value
            .replace(/<(.|\n)*?>/g, '')
            .replaceAll('&nbsp;', ' ')
            .trim().length === 0 &&
        value.indexOf('<img') === -1 &&
        value.indexOf('<iframe') === -1
    );
}
