import struct
import zlib

from .core import TextureCacheError

# the cache stores bare jpeg2000 codestreams. a jp2 file is the same
# codestream inside a handful of boxes, so it can be built without decoding
# anything. ISO/IEC 15444-1 annex I
SOC_MARKER = b"\xff\x4f"
SIZ_MARKER = b"\xff\x51"
SIZ_BYTE_COUNT = 43

JP2_SIGNATURE = b"\x00\x00\x00\x0cjP  \r\n\x87\n"
JP2_BRAND = b"jp2 "
JP2_COMPRESSION_TYPE = 7

ENUM_CS_SRGB = 16
ENUM_CS_GREYSCALE = 17

# the ihdr NC field is two bytes. second life encodes with kakadu, which is
# happy to produce more components than a colour space needs, so this has to
# allow more than the four an rgba image would use
MAX_COMPONENTS = 0xFFFF

CDEF_TYPE_COLOR = 0
CDEF_TYPE_OPACITY = 1
CDEF_TYPE_UNSPECIFIED = 0xFFFF

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_COLOR_TYPES = {1: 0, 2: 4, 3: 2, 4: 6}


def codestream_size(codestream: bytes) -> tuple[int, int, int, int]:
    """Width, height, component count and bit depth, from the SIZ marker"""
    if codestream[:2] != SOC_MARKER or codestream[2:4] != SIZ_MARKER:
        raise TextureCacheError("not a jpeg2000 codestream")

    if len(codestream) < SIZ_BYTE_COUNT:
        raise TextureCacheError(
            f"codestream is {len(codestream)} bytes, too short to hold a SIZ marker"
        )

    xsiz, ysiz, xosiz, yosiz = struct.unpack(">4I", codestream[8:24])
    components = struct.unpack(">H", codestream[40:42])[0]

    # the top bit of Ssiz is the sign flag
    bit_depth = (codestream[42] & 0x7F) + 1

    return xsiz - xosiz, ysiz - yosiz, components, bit_depth


def jp2_box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def wrap_jp2(codestream: bytes) -> bytes:
    """Put a codestream in a jp2 container, byte for byte, without recoding it"""
    width, height, components, bit_depth = codestream_size(codestream)

    if not 0 < components <= MAX_COMPONENTS:
        raise TextureCacheError(f"cannot describe {components} components in a jp2")

    header = jp2_box(
        b"ihdr",
        struct.pack(
            ">IIHBBBB",
            height,
            width,
            components,
            bit_depth - 1,
            JP2_COMPRESSION_TYPE,
            0,
            0,
        ),
    ) + jp2_box(
        b"colr",
        struct.pack(
            ">BBBI",
            1,
            0,
            0,
            ENUM_CS_SRGB if components >= 3 else ENUM_CS_GREYSCALE,
        ),
    )

    color_channels = 1 if components < 3 else 3

    if components > color_channels:
        # the colour space does not account for every channel, so a channel
        # definition box has to say what the rest are
        channels = [
            struct.pack(">HHH", channel, CDEF_TYPE_COLOR, channel + 1)
            for channel in range(color_channels)
        ]

        if components == color_channels + 1:
            # one channel over is alpha, and nothing marks it as such without
            # this. any more than that and there is no telling, so leave them
            # unspecified rather than invent a meaning for them
            channels.append(
                struct.pack(">HHH", components - 1, CDEF_TYPE_OPACITY, 0)
            )
        else:
            channels += [
                struct.pack(">HHH", channel, CDEF_TYPE_UNSPECIFIED, 0)
                for channel in range(color_channels, components)
            ]

        header += jp2_box(
            b"cdef", struct.pack(">H", components) + b"".join(channels)
        )

    return (
        JP2_SIGNATURE
        + jp2_box(b"ftyp", JP2_BRAND + struct.pack(">I", 0) + JP2_BRAND)
        + jp2_box(b"jp2h", header)
        + jp2_box(b"jp2c", codestream)
    )


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload))
    )


def encode_png(width: int, height: int, components: int, pixels: bytes) -> bytes:
    """Encode bottom up raw pixels, as the fast cache stores them, as a png"""
    if components not in PNG_COLOR_TYPES:
        raise TextureCacheError(f"cannot write {components} components as a png")

    expected = width * height * components

    if len(pixels) != expected:
        raise TextureCacheError(
            f"got {len(pixels)} pixel bytes, expected {expected} "
            f"for {width}x{height} in {components} components"
        )

    stride = width * components
    scanlines = []

    # png rows run top down and each is prefixed with its filter type
    for row in reversed(range(height)):
        start = row * stride
        scanlines.append(b"\x00" + pixels[start:start + stride])

    return (
        PNG_SIGNATURE
        + png_chunk(
            b"IHDR",
            struct.pack(
                ">IIBBBBB", width, height, 8, PNG_COLOR_TYPES[components], 0, 0, 0
            ),
        )
        + png_chunk(b"IDAT", zlib.compress(b"".join(scanlines), 9))
        + png_chunk(b"IEND", b"")
    )
