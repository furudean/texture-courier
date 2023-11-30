from enum import Enum, auto
from io import BytesIO
from pathlib import Path
from typing import Callable
from . import core


def loads_bytes_io(p: Path) -> BytesIO:
    return BytesIO(p.read_bytes())


class TextureError(Enum):
    EMPTY = auto()
    WRITE_ERROR = auto()


class Texture:
    index: int
    uuid: str
    entry: core.Entry
    loads: Callable[..., bytes]
    error: TextureError | None = None

    def __init__(self, *, index: int, entry: core.Entry, read: Callable[..., bytes]):
        self.index = index
        self.uuid = entry["uuid"]
        self.entry = entry
        self.loads = read

        if entry["image_size"] <= 0:
            # cache entries can be empty, usually indicated by image_size = -1
            self.error = TextureError.EMPTY

    def __repr__(self):
        return f"<TextureCacheItem {self.uuid}>"


class TextureCache:
    cache_dir: Path
    texture_entries_file: BytesIO
    texture_cache_file: BytesIO

    header: core.Header
    textures: list[Texture]

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
        return iter(self.textures)

    def __repr__(self):
        return f"<TextureCache {self.cache_dir.resolve()}>"

    def refresh(self):
        self.texture_entries_file = loads_bytes_io(self.cache_dir / "texture.entries")
        self.texture_cache_file = loads_bytes_io(self.cache_dir / "texture.cache")

        self.header = core.decode_texture_entries_header(self.texture_entries_file)

        entries = core.decode_texture_entries(
            self.texture_entries_file, entry_count=self.header["entry_count"]
        )

        self.textures = []

        def get_read_bytes(i: int, entry: core.Entry):
            def read_bytes() -> bytes:
                head = core.read_texture_cache(self.texture_cache_file, i)

                if entry["image_size"] <= 601 and entry["body_size"] == 0:
                    # sometimes the file is smaller than 600 bytes, so using the head is
                    # sufficient
                    return head
                else:
                    body = core.read_texture_body(
                        entry["uuid"], cache_dir=self.cache_dir
                    )

                    return head + body

            return lambda: read_bytes()

        for i, entry in enumerate(entries):
            self.textures.append(
                Texture(
                    index=i,
                    entry=entry,
                    read=get_read_bytes(i, entry),
                )
            )

    def get(self, uuid: str) -> Texture | None:
        for texture in self.textures:
            if texture.uuid == uuid:
                return texture

        return None
