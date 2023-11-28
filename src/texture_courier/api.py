from io import BytesIO
from pathlib import Path
from typing import Callable
from . import core


def loads_bytes_io(p: Path) -> BytesIO:
    with open(p, mode="rb") as f:
        return BytesIO(f.read())


class TextureCacheItem:
    entry: core.Entry
    loads: Callable[..., bytes]
    ok: bool | None = None

    def __init__(self, *, entry: core.Entry, read: Callable[..., bytes]):
        self.entry = entry
        self.loads = read

        if entry["image_size"] <= 0:
            # a lot of cache entries are empty, (usually indicated by
            # image_size = -1)
            self.ok = False

    def __repr__(self):
        return f"<TextureCacheItem {self.entry['uuid']}>"


class TextureCache:
    cache_dir: Path
    texture_entries: BytesIO
    texture_cache: BytesIO

    header: core.Header
    cache: list[TextureCacheItem]

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)

        if (
            not self.cache_dir.is_dir()
            or not (self.cache_dir / "texture.entries").exists()
            or not (self.cache_dir / "texture.cache").exists()
        ):
            raise FileNotFoundError("path does not contain a proper texture cache")

        self.refresh()

    def __iter__(self):
        return iter(self.cache)

    def __repr__(self):
        return f"<TextureCache {self.cache_dir.resolve()}>"

    def refresh(self):
        self.texture_entries = loads_bytes_io(self.cache_dir / "texture.entries")
        self.texture_cache = loads_bytes_io(self.cache_dir / "texture.cache")

        self.header = core.decode_header(self.texture_entries)

        entries = core.decode_entries(
            self.texture_entries, entry_count=self.header["entry_count"]
        )

        self.cache = []

        for i, entry in enumerate(entries):
            self.cache.append(
                TextureCacheItem(
                    entry=entry,
                    read=lambda: self.read_bytes(i, entry),
                )
            )

    def read_bytes(self, i: int, entry: core.Entry) -> bytes | None:
        head = core.read_texture_cache(self.texture_cache, i)

        if entry["body_size"] == 0:
            # sometimes the file is smaller than 600 bytes, so using the head is
            # sufficient
            return head
        else:
            body = core.read_texture_body(entry["uuid"], cache_dir=self.cache_dir)

            return head + body
