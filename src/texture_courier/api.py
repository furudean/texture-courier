from collections.abc import Callable, Iterator
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, TypeVar

from watchdog.events import (
    DirModifiedEvent,
    FileModifiedEvent,
    PatternMatchingEventHandler,
)
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from .core import (
    Entry,
    Header,
    Thumbnail,
    decode_texture_entries,
    read_fast_cache,
    read_texture_body,
    read_texture_cache,
    texture_location,
)
from .encode import encode_png, wrap_jp2
from .util import format_bytes

T = TypeVar("T")


def loads_bytes_io(p: Path) -> BytesIO:
    return BytesIO(p.read_bytes())


class Texture(Entry):
    index: int
    body_path: Path
    loads: Callable[[], bytes]
    """Open texture as a bytes object"""
    loads_thumbnail: Callable[[], Thumbnail | None]
    """Read this texture's fast cache thumbnail, if there is one"""

    def __init__(
        self,
        *,
        index: int,
        entry: Entry,
        body_path: Path,
        loads: Callable[[], bytes],
        loads_thumbnail: Callable[[], Thumbnail | None],
    ):
        super().__init__(**entry.__dict__)

        self.index = index
        self.body_path = body_path
        self.loads = loads
        self.loads_thumbnail = loads_thumbnail

    def __repr__(self) -> str:
        size = format_bytes(self.image_size) if not self.is_empty else "empty"
        return f"<Texture {self.uuid}, {self.time}, {size}, is_downloaded={self.is_downloaded()}>"

    def is_downloaded(self) -> bool:
        """Check if the texture file is fully downloaded"""
        return self.is_complete and self.fs_size() == self.cached_size

    def fs_size(self) -> int:
        """Get the size of the texture file on disk"""
        if self.is_empty:
            return 0

        body_size = self.body_path.stat().st_size if self.body_path.is_file() else 0

        return self.head_size + body_size

    def loads_jp2(self) -> bytes:
        """Put the texture in a jp2 container without decoding it

        The cache holds a bare codestream, which most software will not open.
        A jp2 is that same codestream in a few bytes of boxes, so this costs
        very little to do.
        """
        return wrap_jp2(self.loads())

    def loads_thumbnail_png(self) -> bytes | None:
        """Encode the fast cache thumbnail as a png"""

        thumbnail = self.loads_thumbnail()

        if thumbnail is None:
            return None

        return encode_png(
            thumbnail.width, thumbnail.height, thumbnail.components, thumbnail.pixels
        )


class TextureCache:
    cache_dir: Path
    texture_entries_file: BytesIO
    texture_cache_file: BytesIO
    fast_cache_file: BytesIO | None
    """FastCache.cache, absent on caches written before it existed"""

    header: Header
    entries: list[Entry]
    textures: dict[str, Texture]

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        # these are per instance, a class level default would be shared by
        # every cache in the process
        self.entries = []
        self.textures = {}

        if (
            not self.cache_dir.is_dir()
            or not (self.cache_dir / "texture.entries").exists()
            or not (self.cache_dir / "texture.cache").exists()
        ):
            raise FileNotFoundError("path does not contain a proper texture cache")

        self.refresh()

    def __iter__(self) -> Iterator[Texture]:
        return iter(self.textures.values())

    def __reversed__(self) -> Iterator[Texture]:
        return reversed(self.textures.values())

    def __len__(self) -> int:
        return len(self.textures)

    def __repr__(self) -> str:
        total_size = sum(texture.image_size for texture in self)

        return (
            f"<TextureCache {self.cache_dir.resolve()}, "
            f"{self.header.entry_count} entries, "
            f"{format_bytes(total_size)}>"
        )

    def __get_read_bytes(self, i: int, entry: Entry) -> Callable[[], bytes]:
        def read_bytes() -> bytes:
            # the slot is a fixed width, so trim the zero padding that follows
            head = read_texture_cache(self.texture_cache_file, i)[: entry.head_size]

            if entry.body_size == 0:
                return head

            path = texture_location(self.cache_dir, entry.uuid)
            body = read_texture_body(path)

            return head + body

        return read_bytes

    def __get_read_thumbnail(self, i: int) -> Callable[[], Thumbnail | None]:
        def read_thumbnail() -> Thumbnail | None:
            if self.fast_cache_file is None:
                return None

            return read_fast_cache(self.fast_cache_file, i)

        return read_thumbnail

    def refresh(self) -> Iterator[Texture]:
        old_entry_count = self.header.entry_count if hasattr(self, "header") else 0

        self.texture_entries_file = loads_bytes_io(self.cache_dir / "texture.entries")
        self.texture_cache_file = loads_bytes_io(self.cache_dir / "texture.cache")
        self.header = Header.from_texture_entries(self.texture_entries_file)

        fast_cache_path = self.cache_dir / "FastCache.cache"
        self.fast_cache_file = (
            loads_bytes_io(fast_cache_path) if fast_cache_path.is_file() else None
        )

        self.entries = decode_texture_entries(
            self.texture_entries_file,
            entry_count=self.header.entry_count,
        )

        if self.header.entry_count < old_entry_count:
            # the cache was cleared
            self.textures = {}

        changed_textures: dict[str, Texture] = {}

        for i, entry in enumerate(self.entries):
            if entry != self.get(entry.uuid, None):
                changed_textures[entry.uuid] = Texture(
                    index=i,
                    entry=entry,
                    loads=self.__get_read_bytes(i, entry),
                    loads_thumbnail=self.__get_read_thumbnail(i),
                    body_path=texture_location(self.cache_dir, entry.uuid),
                )

        self.textures |= changed_textures

        return iter(changed_textures.values())

    def watch(self, handler: Callable[[list[Texture]], Any]) -> BaseObserver:
        """Watch the cache directory for changes and call the handler function on updates."""

        def on_modified(event: DirModifiedEvent | FileModifiedEvent) -> None:
            changed_textures = list(self.refresh())

            if changed_textures:
                handler(changed_textures)

        event_handler = PatternMatchingEventHandler(patterns=["texture.entries"])
        event_handler.on_modified = on_modified  # type: ignore[method-assign]

        observer = Observer()
        observer.schedule(event_handler, str(self.cache_dir.resolve()))
        observer.start()

        return observer

    def get(self, uuid: str, default: Optional[T] = None) -> Texture | T:
        return self.textures.get(uuid, default)  # type: ignore
