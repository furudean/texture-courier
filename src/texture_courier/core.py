from datetime import datetime
from io import BytesIO
from pathlib import Path
import struct
from uuid import UUID
from typing import Any, Iterator, Self

from .util import format_bytes

HEADER_STRUCT_FORMAT = "fI32sI"
HEADER_BYTE_COUNT = 44

ENTRY_STRUCT_FORMAT = "16BiiI"
ENTRY_BYTE_COUNT = 28

TEXTURE_CACHE_BYTE_COUNT = 600

# FastCache.cache holds one downscaled raw thumbnail per entry
# lltexturecache.cpp:
# `const S32 TEXTURE_FAST_CACHE_ENTRY_OVERHEAD = sizeof(S32) * 4; //w, h, c, level`
# `const S32 TEXTURE_FAST_CACHE_DATA_SIZE = 16 * 16 * 4;`
FAST_CACHE_STRUCT_FORMAT = "4i"
FAST_CACHE_HEADER_BYTE_COUNT = 16
FAST_CACHE_DATA_BYTE_COUNT = 16 * 16 * 4
FAST_CACHE_BYTE_COUNT = FAST_CACHE_HEADER_BYTE_COUNT + FAST_CACHE_DATA_BYTE_COUNT


class TextureCacheError(Exception):
    """Cache not laid out the way this program expects"""


class Header:
    version: str
    address_size: int
    encoder: str
    entry_count: int

    def __init__(self, version: str, address_size: int, encoder: str, entry_count: int):
        self.version = version
        self.address_size = address_size
        self.encoder = encoder
        self.entry_count = entry_count

    def __repr__(self) -> str:
        return (
            "<Header "
            f'version="{self.version}", '
            f"address_size={self.address_size}, "
            f'encoder="{self.encoder}", '
            f"entry_count={self.entry_count}>"
        )

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        return iter(self.__dict__.items())

    @classmethod
    def from_texture_entries(cls, texture_entries: BytesIO) -> Self:
        texture_entries.seek(0)
        raw = texture_entries.read(HEADER_BYTE_COUNT)

        if len(raw) != HEADER_BYTE_COUNT:
            raise TextureCacheError(
                "texture.entries is too small to hold a header"
            )

        unpack = struct.unpack(HEADER_STRUCT_FORMAT, raw)

        header = cls(
            version=f"{unpack[0]:0.2f}",
            address_size=unpack[1],
            encoder=unpack[2].decode("utf-8").replace("\x00", ""),
            entry_count=unpack[3],
        )

        expected = HEADER_BYTE_COUNT + header.entry_count * ENTRY_BYTE_COUNT
        actual = texture_entries.getbuffer().nbytes

        if actual != expected:
            raise TextureCacheError(
                f"texture.entries is {actual} bytes, expected {expected} for "
                f"{header.entry_count} entries"
            )

        return header


class Entry:
    uuid: str
    image_size: int
    body_size: int
    time: datetime

    def __init__(self, uuid: str, image_size: int, body_size: int, time: datetime):
        self.uuid = uuid
        self.image_size = image_size
        self.body_size = body_size
        self.time = time

    def __repr__(self) -> str:
        size = format_bytes(self.image_size) if not self.is_empty else "empty"
        return f"<Entry {self.uuid}, {self.time}, {size}>"

    def __eq__(self, value: object) -> bool:
        return (
            isinstance(value, Entry)
            and self.uuid == value.uuid
            and self.time == value.time
            and self.body_size == value.body_size
        )

    @property
    def is_empty(self) -> bool:
        return self.image_size <= 0

    @property
    def head_size(self) -> int:
        if self.is_empty:
            return 0

        return min(self.image_size, TEXTURE_CACHE_BYTE_COUNT)

    @property
    def cached_size(self) -> int:
        if self.is_empty:
            return 0

        return self.head_size + self.body_size

    @property
    def is_complete(self) -> bool:
        return not self.is_empty and self.image_size == self.cached_size

    @classmethod
    def from_bytes(cls, b: bytes) -> Self:
        unpack = struct.unpack(ENTRY_STRUCT_FORMAT, b)

        uuid = str(UUID(int=int.from_bytes(unpack[0:16], byteorder="big")))
        rest = unpack[16:]

        return cls(
            uuid=uuid,
            image_size=rest[0],
            body_size=rest[1],
            time=datetime.fromtimestamp(rest[2]),
        )


class Thumbnail:
    width: int
    height: int
    components: int
    discard_level: int
    pixels: bytes
    """Raw pixel rows, bottom up, as the viewer hands them to GL"""

    def __init__(
        self,
        width: int,
        height: int,
        components: int,
        discard_level: int,
        pixels: bytes,
    ):
        self.width = width
        self.height = height
        self.components = components
        self.discard_level = discard_level
        self.pixels = pixels

    def __repr__(self) -> str:
        return (
            f"<Thumbnail {self.width}x{self.height}, "
            f"{self.components} components, discard {self.discard_level}>"
        )

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    @classmethod
    def from_bytes(cls, b: bytes) -> Self | None:
        width, height, components, discard_level = struct.unpack(
            FAST_CACHE_STRUCT_FORMAT, b[:FAST_CACHE_HEADER_BYTE_COUNT]
        )
        pixel_count = width * height * components

        # a slot that cannot describe an image was never written to. the
        # thumbnails are not all 16x16, tall and narrow textures keep their
        # aspect ratio, so only the total has to fit
        if (
            width <= 0
            or height <= 0
            or not 0 < components <= 4
            or pixel_count > FAST_CACHE_DATA_BYTE_COUNT
        ):
            return None

        # unlike texture.cache, the rest of the slot is not zeroed, it is
        # whatever the previous occupant left behind
        end = FAST_CACHE_HEADER_BYTE_COUNT + pixel_count

        return cls(
            width=width,
            height=height,
            components=components,
            discard_level=discard_level,
            pixels=b[FAST_CACHE_HEADER_BYTE_COUNT:end],
        )


def read_fast_cache(fast_cache: BytesIO, n: int) -> Thumbnail | None:
    offset = FAST_CACHE_BYTE_COUNT * n

    fast_cache.seek(offset)
    raw = fast_cache.read(FAST_CACHE_BYTE_COUNT)

    if len(raw) != FAST_CACHE_BYTE_COUNT:
        raise TextureCacheError(
            f"failed to read from fast cache at {offset}, "
            f"got {len(raw)} of {FAST_CACHE_BYTE_COUNT} bytes"
        )

    return Thumbnail.from_bytes(raw)


def decode_texture_entries(texture_entries: BytesIO, entry_count: int) -> list[Entry]:
    texture_entries.seek(HEADER_BYTE_COUNT)
    entries = []

    for _ in range(entry_count):
        entry_bytes = texture_entries.read(ENTRY_BYTE_COUNT)

        if len(entry_bytes) != ENTRY_BYTE_COUNT:
            raise TextureCacheError(f"failed to read entry at {texture_entries.tell()}")

        entries.append(Entry.from_bytes(entry_bytes))

    if len(entries) != entry_count:
        raise TextureCacheError(
            f"number of read entries {len(entries)} does not match declared count {entry_count}"
        )

    return entries


def read_texture_cache(texture_cache: BytesIO, n: int) -> bytes:
    offset = TEXTURE_CACHE_BYTE_COUNT * n

    # seeking past the end of a BytesIO is legal and reads back short rather
    # than raising, so the length is what has to be checked. texture.cache
    # lagging behind texture.entries is normal while a viewer is running
    texture_cache.seek(offset)
    head = texture_cache.read(TEXTURE_CACHE_BYTE_COUNT)

    if len(head) != TEXTURE_CACHE_BYTE_COUNT:
        raise TextureCacheError(
            f"failed to read from texture cache at {offset}, "
            f"got {len(head)} of {TEXTURE_CACHE_BYTE_COUNT} bytes"
        )

    return head


def texture_location(cache_dir: Path, uuid: str) -> Path:
    subdir = uuid[0]
    texture_file = uuid + ".texture"

    return cache_dir / subdir / texture_file


def read_texture_body(path: Path) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(f"no texture body at {path}")

    with open(path, "rb") as body_file:
        return body_file.read()
