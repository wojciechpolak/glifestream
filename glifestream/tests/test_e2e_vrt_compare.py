"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops, ImageDraw

from glifestream.tests.e2e.vrt import (
    MASK_BLEED,
    MASK_COLOR,
    PIXEL_TOLERANCE,
    _ignore_mask_edges,
    _mask_halo,
    _mask_map,
    _threshold_diff,
)

SIZE = (100, 100)
BACKGROUND = (240, 240, 240)
MASK_BOX = (20, 20, 60, 60)
INK = (10, 10, 10)


def render(*, mask_box=MASK_BOX, ink_at=None) -> Image.Image:
    image = Image.new('RGB', SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    if mask_box is not None:
        draw.rectangle(mask_box, fill=MASK_COLOR)
    if ink_at is not None:
        image.putpixel(ink_at, INK)
    return image


def visible_diff(expected: Image.Image, actual: Image.Image) -> Image.Image:
    """The comparison `VisualRegressionSession.screenshot` performs."""
    diff = ImageChops.difference(expected, actual)
    return _ignore_mask_edges(
        _threshold_diff(diff, tolerance=PIXEL_TOLERANCE),
        _mask_halo(expected, actual),
    )


def test_mask_map_marks_only_the_masked_pixels():
    found = _mask_map(render())

    assert found.getbbox() == (20, 20, 61, 61)
    assert found.getpixel((40, 40)) == 255
    assert found.getpixel((5, 5)) == 0


def test_mask_map_ignores_a_colour_that_merely_looks_close():
    image = Image.new('RGB', SIZE, (254, 0, 255))

    assert _mask_map(image).getbbox() is None


def test_mask_halo_is_none_without_a_mask():
    plain = render(mask_box=None)

    assert _mask_halo(plain, plain) is None


def test_mask_halo_grows_the_mask_by_the_bleed():
    halo = _mask_halo(render(), render())

    assert halo is not None
    assert halo.getbbox() == (
        20 - MASK_BLEED,
        20 - MASK_BLEED,
        61 + MASK_BLEED,
        61 + MASK_BLEED,
    )


def test_mask_halo_keeps_only_what_both_images_agree_on():
    halo = _mask_halo(render(), render(mask_box=(20, 20, 60, 72)))

    assert halo is not None
    assert halo.getbbox() == (
        20 - MASK_BLEED,
        20 - MASK_BLEED,
        61 + MASK_BLEED,
        61 + MASK_BLEED,
    )


def test_mask_halo_is_none_when_only_one_image_has_a_mask():
    assert _mask_halo(render(), render(mask_box=None)) is None


def test_identical_images_compare_clean():
    assert visible_diff(render(), render()).getbbox() is None


def test_a_border_row_just_outside_the_mask_is_ignored():
    """The real failure: one row of a masked element's own border leaking out."""
    expected = render()
    actual = render(ink_at=(40, 61))

    assert visible_diff(expected, actual).getbbox() is None


@pytest.mark.parametrize('row', [61, 60 + MASK_BLEED])
def test_every_row_within_the_bleed_is_ignored(row):
    actual = render(ink_at=(40, row))

    assert visible_diff(render(), actual).getbbox() is None


def test_the_first_row_beyond_the_bleed_still_fails():
    actual = render(ink_at=(40, 61 + MASK_BLEED))

    assert visible_diff(render(), actual).getbbox() is not None


def test_a_difference_far_from_any_mask_still_fails():
    actual = render(ink_at=(5, 90))

    assert visible_diff(render(), actual).getbbox() is not None


def test_a_mask_that_moved_within_the_bleed_is_tolerated():
    """The accepted cost: a masked element's extent is already volatile."""
    moved = render(mask_box=(20, 20, 60, 60 + MASK_BLEED))

    assert visible_diff(render(), moved).getbbox() is None


def test_a_mask_that_grew_beyond_the_bleed_is_reported():
    moved = render(mask_box=(20, 20, 60, 72))

    assert visible_diff(render(), moved).getbbox() is not None


def test_a_mask_that_vanished_entirely_is_reported():
    assert visible_diff(render(), render(mask_box=None)).getbbox() is not None


def test_the_halo_does_not_hide_a_change_inside_an_unmasked_region():
    expected = render(mask_box=None)
    actual = render(mask_box=None, ink_at=(40, 61))

    assert visible_diff(expected, actual).getbbox() is not None
