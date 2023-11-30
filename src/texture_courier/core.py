from datetime import datetime
from io import BytesIO
from pathlib import Path
import struct
from uuid import UUID
from typing import TypedDict

HEADER_STRUCT_FORMAT = "fI32sI"
HEADER_BYTE_COUNT = 44

ENTRY_STRUCT_FORMAT = "16BiiI"
ENTRY_BYTE_COUNT = 28

TEXTURE_CACHE_BYTE_COUNT = 600


class Header(TypedDict):
    version: str
    address_size: int
    encoder: str
    entry_count: int


class Entry(TypedDict):
    uuid: str
    image_size: int
    body_size: int
    time: datetime


def decode_texture_entries_header(texture_entries: BytesIO) -> Header:
    texture_entries.seek(0)
    header = texture_entries.read(HEADER_BYTE_COUNT)
    unpacked = struct.unpack(HEADER_STRUCT_FORMAT, header)

    return {
        "version": "%0.2f" % unpacked[0],
        "address_size": unpacked[1],
        "encoder": unpacked[2].decode("utf-8").replace("\x00", ""),
        "entry_count": unpacked[3],
    }


def decode_texture_entry(b: bytes) -> Entry:
    unpack = struct.unpack(ENTRY_STRUCT_FORMAT, b)

    uuid = str(UUID(int=int.from_bytes(unpack[0:16], byteorder="big")))
    rest = unpack[16:]

    return {
        "uuid": uuid,
        "image_size": rest[0],
        "body_size": rest[1],
        "time": datetime.fromtimestamp(rest[2]),
    }


def decode_texture_entries(texture_entries: BytesIO, entry_count: int) -> list[Entry]:
    texture_entries.seek(HEADER_BYTE_COUNT)
    entries = []

    for _ in range(entry_count):
        entry_bytes = texture_entries.read(ENTRY_BYTE_COUNT)

        if entry_bytes == b"":
            continue

        entries.append(decode_texture_entry(entry_bytes))

    if len(entries) != entry_count:
        raise Exception(
            f"number of read entries {len(entries)} does not match declared count {entry_count}"
        )

    return entries


def read_texture_cache(texture_cache: BytesIO, n: int) -> bytes:
    try:
        texture_cache.seek(TEXTURE_CACHE_BYTE_COUNT * n)
        return texture_cache.read(TEXTURE_CACHE_BYTE_COUNT)
    except OSError:
        raise Exception(
            f"failed to read from texture cache at {TEXTURE_CACHE_BYTE_COUNT * n}"
        )


def read_texture_body(uuid: str, cache_dir: Path) -> bytes:
    subdir = uuid[0]
    texture_file = uuid + ".texture"

    path_to_body = cache_dir / subdir / texture_file

    if not path_to_body.exists():
        raise FileNotFoundError(f"no texture body at {path_to_body}")

    with open(path_to_body, "rb") as body_file:
        return body_file.read()
