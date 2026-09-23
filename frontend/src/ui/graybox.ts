/*
 *  gLifestream Copyright (C) 2009-2026 Wojciech Polak
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

import { _ } from '../util/i18n';
import { MDOM } from '../util/dom';
import { Overlay } from './overlay';

interface GrayboxOptions {
    src: string;
    type?: string | undefined;
    obj?: HTMLAnchorElement | undefined;
    width?: number | string;
    height?: number | string;
}

// RegExp.$1, the deprecated first group of the last match, typed.
const LastMatch = RegExp as unknown as { $1: string };

let initied = false;
let gb: HTMLDivElement | null = null;

function init(): void {
    if (initied) {
        return;
    }
    gb = document.createElement('div');
    gb.id = 'graybox';
    gb.style.display = 'none';
    document.body.appendChild(gb);
    initied = true;
}

/** Opens the pictures of `ctx`, or of the page, in the lightbox on click. */
function scan(ctx?: HTMLElement | JQuery): void {
    init();
    const $imgs = $<HTMLAnchorElement>('.thumbnails > a:has(img)', ctx);
    $imgs.each(function (i, v) {
        this.rel = ($(v).closest('article').get(0) as HTMLElement).id;
    });
    $imgs.click(open_img);
}

function open_img(this: HTMLAnchorElement): boolean {
    let href = this.href;
    let type: string | undefined = undefined;

    if (href.match(/friendfeed-media\.com/)) {
        type = 'image';
    } else if (href.match(/twitpic\.com\/(\w+)/)) {
        href = 'http://twitpic.com/show/full/' + LastMatch.$1;
        type = 'image';
    } else if (href.match(/twitter\.com\//)) {
        href = $(this).data('imgurl');
        type = 'image';
    } else if (href.match(/cdn\.bsky\.app\/img\//)) {
        type = 'image';
    } else if (href.match(/instagram\.com\/p\/([\w-]+)\/?/)) {
        href = 'https://instagram.com/p/' + LastMatch.$1 + '/media/?size=l';
        type = 'image';
    } else if (href.match(/instagr\.am\/p\/([\w-]+)\/?/)) {
        href = 'https://instagram.com/p/' + LastMatch.$1 + '/media/?size=l';
        type = 'image';
    } else if (href.match(/yfrog\.com\/(\w+)/)) {
        href = 'https://yfrog.com/' + LastMatch.$1 + ':iphone';
        type = 'image';
    } else if (href.match(/bp\.blogspot\.com/)) {
        href = href.replace(/-h\//, '/');
    }

    return open({
        src: href,
        type: type,
        obj: this,
    });
}

function open(opts: GrayboxOptions): boolean {
    const src = opts.src;
    const width = opts.width || 425;
    const height = opts.height || 344;
    let type = opts.type || undefined;
    const obj = opts.obj || undefined;

    if (!type) {
        if (
            src.match(/(\.jpg$|\.jpeg$|@jpeg$|\.webp$|\.avif$|\.heif$|\.png$|\.gif$)/i)
        ) {
            type = 'image';
        } else {
            return true;
        }
    }

    if ('fancybox' in ($ as object)) {
        let imgs = [{ src: src }];
        let index = 0;
        const anchor = obj as HTMLAnchorElement;
        if (anchor.rel && anchor.rel !== '' && anchor.rel !== 'nofollow') {
            const $r = $<HTMLAnchorElement>('a[rel=' + anchor.rel + ']');
            if ($r.length > 1) {
                imgs = [];
                $r.each(function (i, v) {
                    imgs.push({ src: v.href });
                    if (src === v.href) {
                        index = i;
                    }
                });
            }
        }
        $.fancybox.open(imgs, {
            type: type,
            index: index,
            centerOnScroll: true,
            overlayColor: 'black',
            overlayOpacity: 0.8,
            padding: 2,
            margin: 15,
            transitionIn: 'elastic',
            transitionOut: 'fade',
            speedOut: 200,
            loop: true,
        });
        return false;
    }

    const box = gb as HTMLDivElement;
    Overlay.enable();
    box.innerHTML = '<div class="loading">' + _('Loading...') + '</div>';
    if (typeof width == 'number') {
        box.style.width = width + 'px';
    } else {
        box.style.width = width;
    }
    if (typeof height == 'number') {
        box.style.height = height + 'px';
    } else {
        box.style.height = height;
    }
    box.style.position = 'absolute';
    MDOM.center(box, $(box).width(), $(box).height());
    box.style.display = 'block';

    $('#overlay').click(close);
    document.onkeydown = function (e) {
        let code;
        if (!e) {
            e = window.event as KeyboardEvent;
        }
        if (e.keyCode) {
            code = e.keyCode;
        } else if (e.which) {
            code = e.which;
        }
        if (code === 27) {
            /* escape */
            close();
            return false;
        }
        return true;
    };

    if (type === 'image') {
        const img = new Image();
        img.src = src;
        img.onerror = close;
        if (img.complete) {
            show_image.call(img);
        } else {
            img.onload = show_image;
        }
    }
    return false;
}

function close(): void {
    const box = gb as HTMLDivElement;
    document.onkeydown = null;
    box.style.display = 'none';
    box.innerHTML = '';
    Overlay.disable();
}

function show_image(this: GlobalEventHandlers): void {
    const box = gb as HTMLDivElement;
    if (box.style.display !== 'block') {
        return;
    }
    const img = this as HTMLImageElement;
    let nscale;
    const maxWidth = ($(window).width() as number) - 100;
    if (img.width > maxWidth) {
        nscale = maxWidth / img.width;
        img.width = maxWidth;
        img.height = img.height * nscale;
    }
    const maxHeight = ($(window).height() as number) - 50;
    if (img.height > maxHeight) {
        nscale = maxHeight / img.height;
        img.height = maxHeight;
        img.width = img.width * nscale;
    }
    MDOM.center(box, img.width, img.height);
    $(box).animate(
        {
            width: img.width + 'px',
            height: img.height + 'px',
        },
        500,
        function () {
            box.innerHTML = '';
            box.appendChild(img);
        },
    );
}

export const Graybox = { init, scan, open_img, open, close };
