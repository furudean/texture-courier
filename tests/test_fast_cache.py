import struct

from texture_courier.core import (
    FAST_CACHE_DATA_BYTE_COUNT,
    FAST_CACHE_MAX_DISCARD_LEVEL,
    Thumbnail,
)

# a slot the viewer has filled, and the rest of it left as it was found
WRITTEN = struct.pack("4i", 16, 16, 4, 5) + bytes(range(256)) * 4


def slot(width: int, height: int, components: int, discard_level: int) -> bytes:
    header = struct.pack("4i", width, height, components, discard_level)

    return header + WRITTEN[len(header) :]


def test_a_written_slot_reads_back() -> None:
    thumbnail = Thumbnail.from_bytes(WRITTEN)

    assert thumbnail is not None
    assert (thumbnail.dimensions, thumbnail.components, thumbnail.discard_level) == ((16, 16), 4, 5)
    assert len(thumbnail.pixels) == FAST_CACHE_DATA_BYTE_COUNT


def test_a_slot_that_cannot_describe_an_image_is_nothing() -> None:
    """Nothing marks a slot as unwritten, so a header that makes no sense is the only sign"""
    assert Thumbnail.from_bytes(slot(0, 16, 4, 5)) is None
    assert Thumbnail.from_bytes(slot(16, -16, 4, 5)) is None
    assert Thumbnail.from_bytes(slot(16, 16, 5, 5)) is None
    assert Thumbnail.from_bytes(slot(16, 16, 0, 5)) is None
    assert Thumbnail.from_bytes(slot(64, 64, 4, 5)) is None


def test_a_discard_level_that_could_not_be_one_is_nothing() -> None:
    """The level doubles a size back up, so junk in that field is not a small mistake"""
    assert Thumbnail.from_bytes(slot(16, 16, 4, -1)) is None
    assert Thumbnail.from_bytes(slot(16, 16, 4, FAST_CACHE_MAX_DISCARD_LEVEL + 1)) is None
    assert Thumbnail.from_bytes(slot(16, 16, 4, 0)) is not None
    assert Thumbnail.from_bytes(slot(16, 16, 4, FAST_CACHE_MAX_DISCARD_LEVEL)) is not None
