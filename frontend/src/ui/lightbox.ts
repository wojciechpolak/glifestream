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

// The lightbox of entry pictures: PhotoSwipe, over the entry's thumbnails.

import PhotoSwipe from 'photoswipe';
import type { SlideData } from 'photoswipe';
import 'photoswipe/style.css';

import { listen } from '../util/dom';

type Slide = NonNullable<PhotoSwipe['currSlide']>;

const IMAGE = /(\.jpg$|\.jpeg$|@jpeg$|\.webp$|\.avif$|\.heif$|\.png$|\.gif$)/i;

/** Opens the pictures of `ctx`, or of the page, in the lightbox on click. */
function scan(ctx?: HTMLElement | HTMLElement[]): void {
    const roots = ctx === undefined ? [document] : Array.isArray(ctx) ? ctx : [ctx];
    for (const root of roots) {
        for (const link of root.querySelectorAll<HTMLAnchorElement>(
            '.thumbnails > a',
        )) {
            if (link.querySelector('img')) {
                link.rel = (link.closest('article') as HTMLElement).id;
                listen(link, 'click', open_img);
            }
        }
    }
}

/** The picture a thumbnail link opens: its href, or the image a service shows. */
function picture_of(link: HTMLAnchorElement): { src: string; image: boolean } {
    const href = link.href;
    let m: RegExpMatchArray | null;
    if (/twitter\.com\//.test(href)) {
        return { src: link.dataset['imgurl'] as string, image: true };
    } else if (/cdn\.bsky\.app\/img\//.test(href)) {
        return { src: href, image: true };
    } else if ((m = href.match(/instagram\.com\/p\/([\w-]+)\/?/))) {
        return {
            src: 'https://instagram.com/p/' + m[1] + '/media/?size=l',
            image: true,
        };
    }
    const src = /bp\.blogspot\.com/.test(href) ? href.replace(/-h\//, '/') : href;
    return { src, image: IMAGE.test(src) };
}

function open_img(target: HTMLElement): boolean {
    const link = target as HTMLAnchorElement;
    const { src, image } = picture_of(link);
    if (!image) {
        return true;
    }

    let links = [link];
    if (link.rel && link.rel !== 'nofollow') {
        const group = document.querySelectorAll<HTMLAnchorElement>(
            'a[rel="' + CSS.escape(link.rel) + '"]',
        );
        if (group.length > 1) {
            links = Array.from(group);
        }
    }
    const index = Math.max(
        0,
        links.findIndex((a) => a.href === src),
    );
    const slides = links.map((a) => slide_data(links.length > 1 ? a.href : src, a));
    open(slides, index);
    return false;
}

/**
 * A slide of a picture whose size is not known until it loads. It starts
 * with the thumbnail's shape, as wide as the window, and fit_natural() sets
 * the real size once the picture is in.
 */
function slide_data(src: string, link: HTMLAnchorElement): SlideData {
    const thumb = link.querySelector('img');
    const w = window.innerWidth;
    let h = window.innerHeight;
    if (thumb && thumb.naturalWidth && thumb.naturalHeight) {
        h = Math.round((w * thumb.naturalHeight) / thumb.naturalWidth);
    }
    return { src, w, h };
}

/** Gives a slide the size of its loaded picture. */
function fit_natural(slide: Slide | undefined): void {
    const img = slide?.content.element;
    if (!slide || !(img instanceof HTMLImageElement) || !img.complete) {
        return;
    }
    const { naturalWidth: w, naturalHeight: h } = img;
    if (!w || !h || (slide.width === w && slide.height === h)) {
        return;
    }
    slide.content.width = slide.width = w;
    slide.content.height = slide.height = h;
    slide.resize();
}

function open(slides: SlideData[], index: number): void {
    const pswp = new PhotoSwipe({
        dataSource: slides,
        index,
        loop: true,
        bgOpacity: 0.98,
        showHideAnimationType: 'fade',
    });
    pswp.on('loadComplete', ({ slide, isError }) => {
        if (!isError) {
            fit_natural(slide);
        }
    });
    pswp.on('slideActivate', ({ slide }) => fit_natural(slide));
    pswp.init();
}

export const Lightbox = { scan };
