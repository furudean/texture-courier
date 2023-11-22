from io import BytesIO
from pathlib import Path
import struct
from uuid import UUID

HEADER_STRUCT_FORMAT = "fI32sI"
HEADER_BYTE_COUNT = 44

ENTRY_STRUCT_FORMAT = "16BiiI"
ENTRY_BYTE_COUNT = 28

TEXTURE_CACHE_BYTE_COUNT = 600


def loads_bytes(p: Path) -> BytesIO:
    with open(p, mode="rb") as f:
        return BytesIO(f.read())


def decode_header(b: BytesIO):
    b.seek(0)
    header = b.read(HEADER_BYTE_COUNT)
    unpacked = struct.unpack(HEADER_STRUCT_FORMAT, header)

    return {
        "version": "%0.2f" % unpacked[0],
        "address_size": unpacked[1],
        "encoder": unpacked[2].decode("utf-8").replace("\x00", ""),
        "entry_count": unpacked[3],
    }


def decode_entry(b: bytes):
    unpack = struct.unpack(ENTRY_STRUCT_FORMAT, b)

    uuid = str(UUID(int=int.from_bytes(unpack[0:16], byteorder="big")))
    rest = unpack[16:]

    return {
        "uuid": uuid,
        "image_size": rest[0],
        "body_size": rest[1],
        "time": rest[2],
    }


def decode_entries(b: BytesIO, entry_count: int):
    b.seek(HEADER_BYTE_COUNT)
    entries = []

    for _ in range(entry_count):
        entry_bytes = b.read(ENTRY_BYTE_COUNT)

        entries.append(decode_entry(entry_bytes))

    if len(entries) != entry_count:
        print(
            f"number of read entries {len(entries)} does not match expected count {entry_count}"
        )

    return entries


def read_texture_cache(texture_cache: BytesIO, n: int) -> bytes | None:
    try:
        texture_cache.seek(TEXTURE_CACHE_BYTE_COUNT * n)
        return texture_cache.read(TEXTURE_CACHE_BYTE_COUNT)
    except OSError:
        print(f"failed to read from texture cache at {TEXTURE_CACHE_BYTE_COUNT * n}")
        return None


def read_texture_body(uuid: str, cache_dir: Path) -> bytes | None:
    subdir = uuid[0]
    texture_file = uuid + ".texture"

    path_to_body = cache_dir / subdir / texture_file

    if not path_to_body.exists():
        return None

    with open(path_to_body, "rb") as body_file:
        return body_file.read()
