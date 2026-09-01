import pytest
from conftest import sample_textures
from spec import boxes, decode_png, parse_ihdr

from texture_courier import Texture, TextureCache, Thumbnail
from texture_courier.encode import codestream_size, wrap_jp2

SAMPLES = sample_textures()


def test_the_fixture_cache_is_worth_testing_against(
    cache: TextureCache, textures: list[Texture], thumbnails: list[tuple[Texture, Thumbnail]]
) -> None:
    """A cache that lost its interesting entries would pass everything below"""
    assert len(textures) > 100
    assert len(thumbnails) > 100
    assert cache.has_fastcache

    # the two shapes worth having: more components than a colour space can
    # account for, and a thumbnail that is not the usual 16x16
    assert "5 components" in SAMPLES
    assert {thumbnail.dimensions for _, thumbnail in thumbnails} > {(16, 16)}


@pytest.mark.parametrize("texture", SAMPLES.values(), ids=SAMPLES.keys())
def test_a_wrapped_texture_describes_itself_correctly(texture: Texture) -> None:
    original = texture.codestream()
    width, height, components, bit_depth = codestream_size(original)

    jp2 = wrap_jp2(original)
    ihdr = parse_ihdr(boxes(boxes(jp2)[b"jp2h"])[b"ihdr"])

    assert (ihdr.width, ihdr.height, ihdr.components, ihdr.bit_depth) == (
        width,
        height,
        components,
        bit_depth,
    )


def test_every_texture_keeps_its_bytes(textures: list[Texture]) -> None:
    for texture in textures:
        original = texture.codestream()

        assert boxes(wrap_jp2(original))[b"jp2c"] == original, texture.uuid


def test_wrapping_costs_a_header_and_nothing_else(textures: list[Texture]) -> None:
    for texture in textures:
        overhead = len(texture.jpeg_2000()) - len(texture.codestream())

        assert 0 < overhead < 256, texture.uuid


def test_every_thumbnail_encodes(thumbnails: list[tuple[Texture, Thumbnail]]) -> None:
    for texture, thumbnail in thumbnails:
        png = decode_png(thumbnail.png())

        assert (png.width, png.height, png.components) == (
            thumbnail.width,
            thumbnail.height,
            thumbnail.components,
        ), texture.uuid
        assert b"".join(reversed(png.rows)) == thumbnail.pixels, texture.uuid


def test_every_thumbnail_says_what_it_was_reduced_from(thumbnails: list[tuple[Texture, Thumbnail]]) -> None:
    for texture, thumbnail in thumbnails:
        width, height = thumbnail.source_dimensions

        # a discard level is a count of halvings, so the size it came from is
        # the size it is, doubled that many times and never smaller
        assert (width, height) >= thumbnail.dimensions, texture.uuid
        assert (width >> thumbnail.discard_level, height >> thumbnail.discard_level) == thumbnail.dimensions, texture.uuid
