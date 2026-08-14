"""Readers and writers for the formats under test

Written from the specs rather than in terms of texture_courier.encode. A test
that parses with the same code that wrote has only proved that the code agrees
with itself.
"""

from dataclasses import dataclass
import struct
import zlib
from typing import Iterator

SOC_MARKER = b"\xff\x4f"
SIZ_MARKER = b"\xff\x51"

JP2_SIGNATURE = b"\x00\x00\x00\x0cjP  \r\n\x87\n"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# colour type to samples per pixel, ISO/IEC 15948 table 11.1
PNG_COMPONENTS = {0: 1, 2: 3, 4: 2, 6: 4}


def codestream(
    *,
    width: int = 64,
    height: int = 64,
    components: int = 3,
    bit_depth: int = 8,
    origin: tuple[int, int] = (0, 0),
    tail: bytes = b"",
) -> bytes:
    """A codestream with a real SIZ marker and nothing else worth decoding

    Wrapping never looks past the image header, so the entropy coded data a
    real texture carries after this would add nothing to test.
    """
    x_origin, y_origin = origin

    return (
        SOC_MARKER
        + SIZ_MARKER
        + struct.pack(">HH", 38 + 3 * components, 0)
        + struct.pack(
            ">8I",
            width + x_origin,  # Xsiz is the full reference grid, origin included
            height + y_origin,
            x_origin,
            y_origin,
            width,  # one tile covering the image
            height,
            0,
            0,
        )
        + struct.pack(">H", components)
        + bytes([bit_depth - 1, 1, 1]) * components
        + tail
    )


@dataclass(frozen=True)
class Box:
    kind: bytes
    payload: bytes


def iter_boxes(b: bytes) -> Iterator[Box]:
    """Walk a jp2 box structure, checking every declared length on the way"""
    offset = 0

    while offset < len(b):
        remaining = len(b) - offset

        if remaining < 8:
            raise ValueError(f"{remaining} bytes left over, too few for a box header")

        length, kind = struct.unpack(">I4s", b[offset:offset + 8])

        # a length of 0 means the box runs to the end of the file and 1 means a
        # 64 bit length follows. the encoder emits neither
        if length < 8 or length > remaining:
            raise ValueError(f"box {kind!r} declares {length} bytes, {remaining} remain")

        yield Box(kind, b[offset + 8:offset + length])

        offset += length


def boxes(b: bytes) -> dict[bytes, bytes]:
    """Box payloads by kind, for structures that hold each kind at most once"""
    return {box.kind: box.payload for box in iter_boxes(b)}


@dataclass(frozen=True)
class Ihdr:
    height: int
    width: int
    components: int
    bit_depth: int
    compression: int


def parse_ihdr(payload: bytes) -> Ihdr:
    height, width, components, depth, compression = struct.unpack(">IIHBB", payload[:12])

    # the top bit of BPC is the sign flag, the rest is depth less one
    return Ihdr(height, width, components, (depth & 0x7F) + 1, compression)


def parse_colr(payload: bytes) -> int:
    """The enumerated colour space of a colr box"""
    method, _precedence, _approximation = struct.unpack(">BBB", payload[:3])

    if method != 1:
        raise ValueError(f"colr method {method} is not an enumerated colour space")

    return int(struct.unpack(">I", payload[3:7])[0])


def parse_cdef(payload: bytes) -> dict[int, tuple[int, int]]:
    """Channel index to its (type, association) pair"""
    count = struct.unpack(">H", payload[:2])[0]
    channels = {}

    for i in range(count):
        start = 2 + i * 6
        channel, kind, association = struct.unpack(">HHH", payload[start:start + 6])
        channels[channel] = (kind, association)

    return channels


@dataclass(frozen=True)
class Chunk:
    kind: bytes
    payload: bytes


def iter_chunks(b: bytes) -> Iterator[Chunk]:
    """Walk png chunks, checking every crc on the way"""
    if b[:8] != PNG_SIGNATURE:
        raise ValueError("not a png")

    offset = 8

    while offset < len(b):
        if len(b) - offset < 8:
            raise ValueError(f"{len(b) - offset} bytes left over, too few for a chunk header")

        length, kind = struct.unpack(">I4s", b[offset:offset + 8])
        payload = b[offset + 8:offset + 8 + length]
        checksum = b[offset + 8 + length:offset + 12 + length]

        if len(payload) != length or len(checksum) != 4:
            raise ValueError(f"chunk {kind!r} runs past the end of the file")

        if struct.unpack(">I", checksum)[0] != zlib.crc32(kind + payload):
            raise ValueError(f"chunk {kind!r} has a bad crc")

        yield Chunk(kind, payload)

        offset += 12 + length


@dataclass(frozen=True)
class Png:
    width: int
    height: int
    components: int
    rows: tuple[bytes, ...]
    """Pixel rows, top down, the way png stores them"""


def decode_png(b: bytes) -> Png:
    chunks = list(iter_chunks(b))
    kinds = [chunk.kind for chunk in chunks]

    if not kinds or kinds[0] != b"IHDR" or kinds[-1] != b"IEND":
        raise ValueError(f"png chunks are {kinds!r}")

    width, height, depth, colour_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", chunks[0].payload
    )

    if depth != 8:
        raise ValueError(f"{depth} bit samples")

    if compression != 0 or filter_method != 0 or interlace != 0:
        raise ValueError("unexpected compression, filter or interlace method")

    if colour_type not in PNG_COMPONENTS:
        raise ValueError(f"colour type {colour_type}")

    components = PNG_COMPONENTS[colour_type]
    data = zlib.decompress(b"".join(chunk.payload for chunk in chunks if chunk.kind == b"IDAT"))
    stride = width * components

    if len(data) != height * (stride + 1):
        raise ValueError(f"{len(data)} bytes of scanline for {width}x{height} in {components} components")

    rows = []

    for y in range(height):
        start = y * (stride + 1)

        if data[start] != 0:
            raise ValueError(f"row {y} uses filter {data[start]}")

        rows.append(data[start + 1:start + 1 + stride])

    return Png(width, height, components, tuple(rows))
