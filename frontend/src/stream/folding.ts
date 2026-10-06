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

import { config } from '../config';
import { delegate, h } from '../util/dom';
import { _ } from '../util/i18n';

/**
 * The class that folds an entry's content to `config.fold_lines` lines,
 * which the theme reads as --fold-lines. The theme is the one place that
 * says how tall is too tall: a content folds when, folded, it hides some of
 * itself; on a page of one entry nothing does.
 */
const FOLDED = 'folded';

/** Contents that have a toggle; the others may still grow, as images load. */
const toggles = new WeakMap<HTMLElement, HTMLButtonElement>();

function label(folded: boolean): string {
    return folded ? _('Show more') : _('Show less');
}

/** Makes `toggle` say what it does to a content that is `folded` or not. */
function update_toggle(toggle: HTMLElement, folded: boolean): void {
    toggle.textContent = label(folded);
    toggle.setAttribute('aria-expanded', String(!folded));
}

/** Folds `content` if it is too tall, and gives it a toggle to unfold. */
function fold(content: HTMLElement): void {
    if (config.fold_lines <= 0 || toggles.has(content)) {
        return;
    }
    content.classList.add(FOLDED);
    if (content.scrollHeight <= content.clientHeight + 1) {
        content.classList.remove(FOLDED);
        return;
    }
    const article = content.closest('article');
    if (!content.id && article?.id) {
        content.id = article.id + '-content';
    }
    const toggle = h('button', { type: 'button', className: 'show-more' });
    update_toggle(toggle, true);
    toggle.setAttribute('aria-controls', content.id);
    content.after(toggle);
    toggles.set(content, toggle);
}

/** Folds the entry contents inside `root` that are too tall. */
export function fold_long_contents(root: ParentNode): void {
    for (const content of root.querySelectorAll<HTMLElement>('.entry-content')) {
        fold(content);
    }
}

/**
 * Decides again after the width changed: a content may have become too
 * tall, or a folded one may now fit. One the reader unfolded stays so.
 */
function refit(content: HTMLElement): void {
    const toggle = toggles.get(content);
    if (!toggle) {
        fold(content);
        return;
    }
    if (
        content.classList.contains(FOLDED) &&
        content.scrollHeight <= content.clientHeight + 1
    ) {
        content.classList.remove(FOLDED);
        toggle.remove();
        toggles.delete(content);
    }
}

function toggle_content(toggle: HTMLElement): boolean {
    const content = toggle.previousElementSibling;
    if (!(content instanceof HTMLElement)) {
        return false;
    }
    const folded = content.classList.toggle(FOLDED);
    update_toggle(toggle, folded);
    // Folding a long entry read to its end would leave the reader far below it.
    const article = content.closest('article');
    if (folded && article && article.getBoundingClientRect().top < 0) {
        article.scrollIntoView();
    }
    return false;
}

/**
 * Unfolds the folded content that holds `el`, as its toggle would: a player
 * the reader opened there would otherwise start below the fold, unseen.
 */
export function unfold(el: Element): void {
    const content = el.closest<HTMLElement>('.entry-content.' + FOLDED);
    const toggle = content && toggles.get(content);
    if (content && toggle) {
        content.classList.remove(FOLDED);
        update_toggle(toggle, false);
    }
}

/** Folds the stream's long entries, now and as their images load. */
export function init_folding(stream: HTMLElement): void {
    stream.style.setProperty('--fold-lines', String(config.fold_lines));
    delegate(stream, 'click', 'button.show-more', toggle_content);
    // An image that loads can make a short entry long.
    stream.addEventListener(
        'load',
        function (event) {
            const target = event.target;
            if (target instanceof HTMLImageElement) {
                const content = target.closest<HTMLElement>('.entry-content');
                if (content) {
                    fold(content);
                }
            }
        },
        true,
    );
    let pending = false;
    window.addEventListener('resize', function () {
        if (pending) {
            return;
        }
        pending = true;
        requestAnimationFrame(function () {
            pending = false;
            for (const content of stream.querySelectorAll<HTMLElement>(
                '.entry-content',
            )) {
                refit(content);
            }
        });
    });
    fold_long_contents(stream);
}
