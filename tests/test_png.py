import struct

from hypothesis import given, settings, strategies as st
import pytest

from texture_courier.core import TextureCacheError
from texture_courier.encode import encode_png

from spec import decode_png, iter_chunks


def rows(width: int, height: int, components: int) -> list[bytes]:
    """An image where every row differs, so a flip cannot go unnoticed"""
    stride = width * components

    return [bytes((y * stride + i) % 256 for i in range(stride)) for y in range(height)]


@st.composite
def images(draw: st.DrawFn) -> tuple[int, int, int, bytes]:
    width = draw(st.integers(min_value=1, max_value=24))
    height = draw(st.integers(min_value=1, max_value=24))
    components = draw(st.sampled_from((1, 2, 3, 4)))
    size = width * height * components
    pixels = draw(st.binary(min_size=size, max_size=size))

    return width, height, components, pixels


def test_rows_come_out_the_other_way_up() -> None:
    """The fast cache hands out rows bottom up, the way GL wants them"""
    bottom_up = [b"\x00\x00\x00", b"\x01\x01\x01", b"\x02\x02\x02"]

    png = decode_png(encode_png(1, 3, 3, b"".join(bottom_up)))

    assert png.rows == (b"\x02\x02\x02", b"\x01\x01\x01", b"\x00\x00\x00")


@pytest.mark.parametrize("size", [(1, 1), (16, 16), (4, 64), (64, 4), (1, 32)])
@pytest.mark.parametrize("components", [1, 2, 3, 4])
def test_pixels_survive_a_round_trip(size: tuple[int, int], components: int) -> None:
    width, height = size
    original = rows(width, height, components)

    png = decode_png(encode_png(width, height, components, b"".join(original)))

    assert (png.width, png.height, png.components) == (width, height, components)
    assert png.rows == tuple(reversed(original))


def test_chunks_are_in_the_order_a_reader_expects() -> None:
    kinds = [chunk.kind for chunk in iter_chunks(encode_png(2, 2, 3, bytes(12)))]

    assert kinds == [b"IHDR", b"IDAT", b"IEND"]


@pytest.mark.parametrize("components,colour_type", [(1, 0), (2, 4), (3, 2), (4, 6)])
def test_colour_type_follows_the_component_count(components: int, colour_type: int) -> None:
    ihdr = next(iter_chunks(encode_png(1, 1, components, bytes(components)))).payload

    assert struct.unpack(">IIBBBBB", ihdr)[3] == colour_type


@pytest.mark.parametrize("components", [0, 5, 8])
def test_rejects_component_counts_png_has_no_colour_type_for(components: int) -> None:
    with pytest.raises(TextureCacheError, match="cannot write"):
        encode_png(1, 1, components, bytes(components))


@pytest.mark.parametrize("pixels", [b"", bytes(11), bytes(13)])
def test_rejects_a_pixel_buffer_that_is_not_the_size_it_claims(pixels: bytes) -> None:
    with pytest.raises(TextureCacheError, match="expected 12"):
        encode_png(2, 2, 3, pixels)


@settings(max_examples=200)
@given(images())
def test_any_image_survives_a_round_trip(image: tuple[int, int, int, bytes]) -> None:
    width, height, components, pixels = image

    # iter_chunks checks every crc on the way, so a decode getting this far is
    # already most of the assertion
    png = decode_png(encode_png(width, height, components, pixels))

    assert (png.width, png.height, png.components) == (width, height, components)
    assert b"".join(reversed(png.rows)) == pixels
