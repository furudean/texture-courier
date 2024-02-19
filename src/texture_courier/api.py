from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, TypeVar
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.events import (
    PatternMatchingEventHandler,
    DirModifiedEvent,
    FileModifiedEvent,
)

from .core import (
    Header,
    Entry,
    read_texture_cache,
    read_texture_body,
    texture_location,
    decode_texture_entries,
)
from .util import format_bytes

from PIL import Image

T = TypeVar("T")


def loads_bytes_io(p: Path) -> BytesIO:
    return BytesIO(p.read_bytes())


class Texture(Entry):
    index: int
    body_path: Path
    loads: Callable[[], bytes]
    """Open texture as a bytes object"""

    def __init__(
        self,
        *,
        index: int,
        entry: Entry,
        body_path: Path,
        loads: Callable[[], bytes],
    ):
        super().__init__(**entry.__dict__)

        self.index = index
        self.body_path = body_path
        self.loads = loads

    def __repr__(self) -> str:
        size = format_bytes(self.image_size) if not self.is_empty else "empty"
        return f"<Texture {self.uuid}, {self.time}, {size}, is_downloaded={self.is_downloaded()}>"

    def is_downloaded(self) -> bool:
        """Check if the texture file is fully downloaded"""
        return self.fs_size() == self.image_size

    def fs_size(self) -> int:
        """Get the size of the texture file on disk"""
        if self.is_empty:
            return 0

        head_size = self.image_size - self.body_size
        body_size = self.body_path.stat().st_size if self.body_path.is_file() else 0

        return head_size + body_size

    def open_image(self) -> Image.Image:
        """Open texture as a pillow image"""

        b = self.loads()
        return Image.open(BytesIO(b), formats=["jpeg2000"])


class TextureCache:
    cache_dir: Path
    texture_entries_file: BytesIO
    texture_cache_file: BytesIO

    header: Header
    entries: list[Entry] = []
    textures: dict[str, Texture] = {}

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)

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
            head = read_texture_cache(self.texture_cache_file, i)

            if entry.image_size <= 601 and entry.body_size == 0:
                # sometimes the file is smaller than 600 bytes, so using the head is
                # sufficient
                return head
            else:
                path = texture_location(self.cache_dir, entry.uuid)
                body = read_texture_body(path)

                return head + body

        return read_bytes

    def refresh(self) -> Iterator[Texture]:
        old_entry_count = self.header.entry_count if hasattr(self, "header") else 0

        self.texture_entries_file = loads_bytes_io(self.cache_dir / "texture.entries")
        self.texture_cache_file = loads_bytes_io(self.cache_dir / "texture.cache")
        self.header = Header.from_texture_entries(self.texture_entries_file)

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
        setattr(event_handler, "on_modified", on_modified)

        observer = Observer()
        observer.schedule(event_handler, str(self.cache_dir.resolve()))
        observer.start()

        return observer

    def get(self, uuid: str, default: Optional[T] = None) -> Texture | T:
        return self.textures.get(uuid, default)  # type: ignore
