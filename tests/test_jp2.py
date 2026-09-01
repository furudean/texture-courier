import struct

import pytest
from hypothesis import given
from hypothesis import strategies as st
from spec import JP2_SIGNATURE, boxes, codestream, iter_boxes, parse_cdef, parse_colr, parse_ihdr

from texture_courier.encode import (
    CDEF_TYPE_COLOR,
    CDEF_TYPE_OPACITY,
    CDEF_TYPE_UNSPECIFIED,
    ENUM_CS_GREYSCALE,
    ENUM_CS_SRGB,
    wrap_jp2,
)
from texture_courier.error import TextureCacheError


def jp2h(jp2: bytes) -> dict[bytes, bytes]:
    """The boxes inside the jp2 header superbox"""
    return boxes(boxes(jp2)[b"jp2h"])


def test_the_codestream_comes_back_untouched() -> None:
    """The whole point of wrapping rather than transcoding"""
    original = codestream(tail=b"entropy coded data would go here")

    assert boxes(wrap_jp2(original))[b"jp2c"] == original


def test_boxes_are_in_the_order_a_reader_expects() -> None:
    kinds = [box.kind for box in iter_boxes(wrap_jp2(codestream()))]

    assert kinds == [b"jP  ", b"ftyp", b"jp2h", b"jp2c"]


def test_signature_comes_first() -> None:
    assert wrap_jp2(codestream()).startswith(JP2_SIGNATURE)


def test_file_is_branded_jp2() -> None:
    ftyp = boxes(wrap_jp2(codestream()))[b"ftyp"]
    brand, minor_version = struct.unpack(">4sI", ftyp[:8])

    assert brand == b"jp2 "
    assert minor_version == 0
    # a reader looks for its own brand in the compatibility list, so ours has
    # to be in there even though it is also the brand
    assert ftyp[8:] == b"jp2 "


@pytest.mark.parametrize("size", [(1, 1), (16, 16), (64, 32), (4, 64), (1024, 1024)])
def test_ihdr_matches_the_codestream(size: tuple[int, int]) -> None:
    width, height = size
    ihdr = parse_ihdr(jp2h(wrap_jp2(codestream(width=width, height=height)))[b"ihdr"])

    assert (ihdr.width, ihdr.height) == (width, height)
    # 7 is "the codestream says", the only legal value for a jp2
    assert ihdr.compression == 7


def test_image_offset_is_taken_off_the_size() -> None:
    """Xsiz and Ysiz measure the reference grid, not the image on it"""
    ihdr = parse_ihdr(jp2h(wrap_jp2(codestream(width=64, height=32, origin=(8, 4))))[b"ihdr"])

    assert (ihdr.width, ihdr.height) == (64, 32)


@pytest.mark.parametrize("bit_depth", [1, 8, 12, 16])
def test_bit_depth_survives(bit_depth: int) -> None:
    ihdr = parse_ihdr(jp2h(wrap_jp2(codestream(bit_depth=bit_depth)))[b"ihdr"])

    assert ihdr.bit_depth == bit_depth


@pytest.mark.parametrize(
    "components,colour_space",
    [(1, ENUM_CS_GREYSCALE), (2, ENUM_CS_GREYSCALE), (3, ENUM_CS_SRGB), (4, ENUM_CS_SRGB), (5, ENUM_CS_SRGB)],
)
def test_colour_space_follows_the_component_count(components: int, colour_space: int) -> None:
    assert parse_colr(jp2h(wrap_jp2(codestream(components=components)))[b"colr"]) == colour_space


@pytest.mark.parametrize("components", [1, 3])
def test_no_cdef_when_the_colour_space_accounts_for_every_channel(components: int) -> None:
    assert b"cdef" not in jp2h(wrap_jp2(codestream(components=components)))


@pytest.mark.parametrize("components", [2, 4])
def test_cdef_marks_the_spare_channel_as_alpha(components: int) -> None:
    """Nothing else in the file says the last channel is opacity"""
    channels = parse_cdef(jp2h(wrap_jp2(codestream(components=components)))[b"cdef"])

    assert len(channels) == components
    assert channels[components - 1] == (CDEF_TYPE_OPACITY, 0)

    for channel in range(components - 1):
        # colour channels are associated one indexed, 0 means the whole image
        assert channels[channel] == (CDEF_TYPE_COLOR, channel + 1)


def test_cdef_leaves_extra_channels_unspecified() -> None:
    """Second Life encodes with kakadu, which emits more than four components

    There is no telling what the extras hold, and guessing alpha would be
    worse than saying nothing. These used to be dropped on the floor instead.
    """
    channels = parse_cdef(jp2h(wrap_jp2(codestream(components=5)))[b"cdef"])

    assert channels == {
        0: (CDEF_TYPE_COLOR, 1),
        1: (CDEF_TYPE_COLOR, 2),
        2: (CDEF_TYPE_COLOR, 3),
        3: (CDEF_TYPE_UNSPECIFIED, 0),
        4: (CDEF_TYPE_UNSPECIFIED, 0),
    }


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\x89PNG\r\n\x1a\n" + bytes(64), id="a png"),
        pytest.param(JP2_SIGNATURE + codestream(), id="already wrapped"),
        pytest.param(codestream()[2:], id="no SOC marker"),
    ],
)
def test_rejects_what_is_not_a_codestream(bad: bytes) -> None:
    with pytest.raises(TextureCacheError, match="not a jpeg2000 codestream"):
        wrap_jp2(bad)


def test_rejects_a_codestream_cut_off_inside_its_header() -> None:
    with pytest.raises(TextureCacheError, match="too short"):
        wrap_jp2(codestream()[:32])


def test_rejects_zero_components() -> None:
    # padded because a zero component SIZ is one byte short of readable
    with pytest.raises(TextureCacheError, match="cannot describe 0 components"):
        wrap_jp2(codestream(components=0, tail=b"\x00"))


@given(
    width=st.integers(min_value=1, max_value=2**16),
    height=st.integers(min_value=1, max_value=2**16),
    components=st.integers(min_value=1, max_value=16),
    bit_depth=st.integers(min_value=1, max_value=38),
)
def test_any_codestream_wraps_into_a_readable_file(width: int, height: int, components: int, bit_depth: int) -> None:
    original = codestream(width=width, height=height, components=components, bit_depth=bit_depth)
    jp2 = wrap_jp2(original)

    # iter_boxes walks the declared lengths, so this also proves the boxes tile
    # the file exactly, with no slack and nothing running off the end
    assert boxes(jp2)[b"jp2c"] == original

    ihdr = parse_ihdr(jp2h(jp2)[b"ihdr"])

    assert (ihdr.width, ihdr.height, ihdr.components, ihdr.bit_depth) == (
        width,
        height,
        components,
        bit_depth,
    )
