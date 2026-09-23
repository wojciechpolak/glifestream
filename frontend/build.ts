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

// Bundles frontend/src into glifestream/static/js/dist, where django-pipeline
// picks the result up for its `main` bundle (see PIPELINE in settings.py).
// esbuild only strips the types; `npm run typecheck` is what checks them.
//
//   node frontend/build.ts            one build
//   node frontend/build.ts --watch    rebuild on every change

import * as esbuild from 'esbuild';

const watch = process.argv.includes('--watch');

const options: esbuild.BuildOptions = {
    absWorkingDir: import.meta.dirname,
    entryPoints: { glifestream: 'src/main.ts' },
    outdir: '../glifestream/static/js/dist',
    bundle: true,
    format: 'iife',
    target: 'es2024',
    charset: 'utf8',
    logLevel: 'info',
    // Pipeline appends this file to jQuery and fancyBox in js/main.js, and a
    // browser would apply the map to that whole file, off by every line in
    // front of ours. So the map is written next to the bundle but not linked,
    // except in watch mode: the development server, with DEBUG on, serves
    // this file on its own.
    sourcemap: watch ? 'linked' : 'external',
};

if (watch) {
    const context = await esbuild.context(options);
    await context.watch();
} else {
    await esbuild.build(options);
}
