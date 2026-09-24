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

import { afterEach, describe, expect, it } from 'vitest';

import { config } from '../config';
import { calculateBoundingBox, convertToOSMBbox, get_map_embed } from './maps';

afterEach(() => {
    config.maps_engine = '';
});

describe('calculateBoundingBox', () => {
    it('spans the radius in latitude on each side of the point', () => {
        const box = calculateBoundingBox(52.23, 21.01, 10);
        const latDiff = (10 / 6371) * (180 / Math.PI);

        expect(box.southwest.lat).toBeCloseTo(52.23 - latDiff, 10);
        expect(box.northeast.lat).toBeCloseTo(52.23 + latDiff, 10);
    });

    it('widens the longitude span away from the equator', () => {
        const equator = calculateBoundingBox(0, 0, 10);
        const north = calculateBoundingBox(60, 0, 10);
        const equatorSpan = equator.northeast.lon - equator.southwest.lon;
        const northSpan = north.northeast.lon - north.southwest.lon;

        expect(northSpan).toBeCloseTo(equatorSpan * 2, 6);
    });
});

describe('convertToOSMBbox', () => {
    it('orders the corners west, south, east, north to 7 places', () => {
        const bbox = convertToOSMBbox({
            southwest: { lat: 1.5, lon: -2.25 },
            northeast: { lat: 3, lon: 4.123456789 },
        });

        expect(bbox).toBe('-2.2500000,1.5000000,4.1234568,3.0000000');
    });
});

describe('get_map_embed', () => {
    it('embeds OpenStreetMap by default, with the point marked', () => {
        config.maps_engine = 'osm';
        const bbox = convertToOSMBbox(calculateBoundingBox(52.23, 21.01, 10));

        const html = get_map_embed('52.23', '21.01');

        expect(html).toContain(
            'https://www.openstreetmap.org/export/embed.html?layer=mapnik' +
                '&bbox=' +
                bbox +
                '&marker=52.23,21.01"',
        );
        expect(html).toContain('?mlat=52.23&mlon=21.01#map=10/52.23/21.01');
    });

    it('shows a Google static map when the config asks for it', () => {
        config.maps_engine = 'google';

        const html = get_map_embed('52.23', '21.01');

        expect(html).toContain('maps.googleapis.com/maps/api/staticmap');
        expect(html).toContain('&markers=52.23,21.01"');
    });
});
