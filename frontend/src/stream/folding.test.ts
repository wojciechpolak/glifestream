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

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { config } from '../config';
import { fold_long_contents, init_folding } from './folding';

/**
 * A folded content shows 100px. The test DOM has no layout, so the entry
 * says how tall its content is: a number, or a function for one that grows.
 */
function entry(id: string, height: number | (() => number)): HTMLElement {
    const tall = typeof height === 'number' ? () => height : height;
    const article = document.createElement('article');
    article.id = id;
    const content = document.createElement('div');
    content.className = 'entry-content';
    Object.defineProperty(content, 'scrollHeight', { get: tall });
    Object.defineProperty(content, 'clientHeight', {
        get: () =>
            content.classList.contains('folded') ? Math.min(tall(), 100) : tall(),
    });
    article.append(content);
    return article;
}

function stream(...articles: HTMLElement[]): HTMLElement {
    const el = document.createElement('div');
    el.id = 'stream';
    el.append(...articles);
    document.body.replaceChildren(el);
    return el;
}

beforeEach(() => {
    document.body.replaceChildren();
});

afterEach(() => {
    config.fold_lines = 20;
});

describe('fold_long_contents', () => {
    it('folds only the contents taller than the folded height', () => {
        const root = stream(entry('entry-1', 400), entry('entry-2', 60));

        fold_long_contents(root);

        const [long, short] = root.querySelectorAll('.entry-content');
        expect(long?.classList.contains('folded')).toBe(true);
        expect(short?.classList.contains('folded')).toBe(false);
        expect(root.querySelectorAll('button.show-more')).toHaveLength(1);
        const toggle = long?.nextElementSibling;
        expect(toggle?.textContent).toBe('Show more');
        expect(toggle?.getAttribute('aria-expanded')).toBe('false');
        expect(toggle?.getAttribute('aria-controls')).toBe('entry-1-content');
        expect(long?.id).toBe('entry-1-content');
    });

    it('folds nothing when the user chose 0 lines', () => {
        config.fold_lines = 0;
        const root = stream(entry('entry-1', 400));

        init_folding(root);

        expect(root.querySelector('.entry-content')?.classList.contains('folded')).toBe(
            false,
        );
        expect(root.querySelectorAll('button.show-more')).toHaveLength(0);
    });

    it('hands the number of lines to the theme', () => {
        config.fold_lines = 8;
        const root = stream(entry('entry-1', 60));

        init_folding(root);

        expect(root.style.getPropertyValue('--fold-lines')).toBe('8');
    });

    it('adds one toggle however often it runs', () => {
        const root = stream(entry('entry-1', 400));

        fold_long_contents(root);
        fold_long_contents(root);

        expect(root.querySelectorAll('button.show-more')).toHaveLength(1);
    });
});

describe('init_folding', () => {
    it('unfolds and folds again with the toggle', () => {
        const root = stream(entry('entry-1', 400));
        init_folding(root);
        const content = root.querySelector('.entry-content') as HTMLElement;
        const toggle = root.querySelector('button.show-more') as HTMLButtonElement;

        toggle.click();
        expect(content.classList.contains('folded')).toBe(false);
        expect(toggle.textContent).toBe('Show less');
        expect(toggle.getAttribute('aria-expanded')).toBe('true');

        toggle.click();
        expect(content.classList.contains('folded')).toBe(true);
        expect(toggle.textContent).toBe('Show more');
        expect(toggle.getAttribute('aria-expanded')).toBe('false');
    });

    it('decides again when the width changes', async () => {
        let height = 400;
        const other = 400;
        const root = stream(
            entry('entry-1', () => height),
            entry('entry-2', other),
        );
        init_folding(root);
        const [first, second] = root.querySelectorAll<HTMLElement>('.entry-content');
        // The reader unfolds the second one.
        const toggle = second?.nextElementSibling;
        expect(toggle).toBeInstanceOf(HTMLButtonElement);
        (toggle as HTMLButtonElement).click();

        height = 60;
        window.dispatchEvent(new Event('resize'));
        await new Promise((resolve) => requestAnimationFrame(resolve));

        // The first now fits, so it loses its toggle; the second stays open.
        expect(first?.classList.contains('folded')).toBe(false);
        expect(first?.nextElementSibling).toBe(null);
        expect(second?.classList.contains('folded')).toBe(false);
        expect(second?.nextElementSibling?.textContent).toBe('Show less');
    });

    it('folds an entry that grows when its image loads', () => {
        let height = 60;
        const article = entry('entry-1', () => height);
        const content = article.querySelector('.entry-content') as HTMLElement;
        const img = document.createElement('img');
        content.append(img);
        const root = stream(article);
        init_folding(root);
        expect(content.classList.contains('folded')).toBe(false);

        height = 400;
        img.dispatchEvent(new Event('load'));

        expect(content.classList.contains('folded')).toBe(true);
        expect(root.querySelectorAll('button.show-more')).toHaveLength(1);
    });
});
