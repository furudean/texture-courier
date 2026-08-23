from collections.abc import Callable, Iterator
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from .core import (
    Entry,
    Header,
    TextureCacheError,
    Thumbnail,
    decode_texture_entries,
    read_fast_cache,
    read_texture_body,
    read_texture_cache,
    texture_location,
)
from .encode import (
    encode_png,
    wrap_jp2,
)
from .util import format_bytes

if TYPE_CHECKING:
    from watchdog.events import DirModifiedEvent, FileModifiedEvent
    from watchdog.observers.api import BaseObserver

T = TypeVar("T")


def loads_bytes_io(p: Path) -> BytesIO:
    return BytesIO(p.read_bytes())


class Texture(Entry):
    index: int
    body_path: Path

    def __init__(
        self,
        *,
        index: int,
        entry: Entry,
        body_path: Path,
        read_head: Callable[[], bytes],
        read_thumbnail: Callable[[], Thumbnail | None],
    ):
        super().__init__(**entry.__dict__)

        self.index = index
        self.body_path = body_path
        self.__read_head = read_head
        self.__read_thumbnail = read_thumbnail

    def __repr__(self) -> str:
        size = format_bytes(self.image_size) if not self.is_empty else "empty"

        return f"<Texture {self.uuid}, {self.time}, {size}, whole={self.whole()}>"

    def whole(self) -> bool:
        """Whether the cache claims to hold the whole image, head and body together

        Only the entry's account of itself, which costs nothing to ask for.
        Whether the bytes bear it out is settled when they are read.
        """
        return self.is_complete

    def __incomplete(self) -> TextureCacheError:
        return TextureCacheError(f"{self.uuid} holds {self.cached_size} of {self.image_size} bytes")

    def __verify(self, head: bytes, body_size: int, tail: bytes) -> None:
        """The one account of what a whole texture is, for whichever bytes the caller holds"""
        if not self.is_complete:
            raise self.__incomplete()

        if body_size != self.body_size:
            raise TextureCacheError(f"{self.uuid} has a {body_size} byte body, entry describes {self.body_size}")

    def fs_size(self) -> int:
        """Get the size of the texture file on disk"""
        if self.is_empty:
            return 0

        body_size = self.body_path.stat().st_size if self.body_path.is_file() else 0

        return self.head_size + body_size

    def codestream(self, *, verify: bool = True) -> bytes:
        """Open the bare codestream as a bytes object"""
        # the body runs to megabytes, so the entry gets its say before the read
        if verify and not self.is_complete:
            raise self.__incomplete()

        head = self.__read_head()
        body = b"" if self.body_size == 0 else read_texture_body(self.body_path)
        codestream = head + body

        if verify:
            # against the bytes in hand rather than the file, a viewer writing
            # to the cache can move the body between a check and the read after
            self.__verify(head, len(body), codestream)

        return codestream

    def jpeg_2000(self, *, verify: bool = True) -> bytes:
        """Wrap the codestream in a JPEG 2000 container"""
        return wrap_jp2(self.codestream(verify=verify))

    def thumbnail_png(self) -> bytes | None:
        """Encode the item's thumbnail as a png"""

        thumbnail = self.__read_thumbnail()

        if thumbnail is None:
            return None

        return encode_png(thumbnail.width, thumbnail.height, thumbnail.components, thumbnail.pixels)


class TextureCache:
    cache_dir: Path
    texture_entries_file: BytesIO
    texture_cache_file: BytesIO

    header: Header
    entries: list[Entry]
    textures: dict[str, Texture]

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.entries = []
        self.textures = {}
        self.__entries_raw = b""
        self.__fast_cache_file: BytesIO | None = None

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

        return f"<TextureCache {self.cache_dir.resolve()}, {len(self)} textures, {format_bytes(total_size)}>"

    @property
    def fast_cache_file(self) -> BytesIO | None:
        """FastCache.cache, read on first use, absent on caches written before it

        Bigger than the rest of the cache put together and untouched unless
        somebody asks for a thumbnail, so refreshing does not pay for it.
        """
        if self.__fast_cache_file is None:
            path = self.cache_dir / "FastCache.cache"
            self.__fast_cache_file = loads_bytes_io(path) if path.is_file() else None

        return self.__fast_cache_file

    def __get_read_head(self, i: int, entry: Entry) -> Callable[[], bytes]:
        def read_head() -> bytes:
            # the slot is a fixed width, so trim the zero padding that follows
            return read_texture_cache(self.texture_cache_file, i)[: entry.head_size]

        return read_head

    def __get_read_thumbnail(self, i: int) -> Callable[[], Thumbnail | None]:
        def read_thumbnail() -> Thumbnail | None:
            if self.fast_cache_file is None:
                return None

            return read_fast_cache(self.fast_cache_file, i)

        return read_thumbnail

    def refresh(self) -> Iterator[Texture]:
        entries_raw = (self.cache_dir / "texture.entries").read_bytes()

        # a running viewer writes this file constantly and most of those writes
        # leave every entry saying what it said before. comparing the bytes
        # costs a memcmp, decoding them to find out costs fifty thousand
        # timestamps and uuids
        if entries_raw == self.__entries_raw:
            return iter(())

        self.__entries_raw = entries_raw
        self.texture_entries_file = BytesIO(entries_raw)
        self.header = Header.from_texture_entries(self.texture_entries_file)

        self.entries = decode_texture_entries(
            self.texture_entries_file,
            entry_count=self.header.entry_count,
        )

        # only worth reading once an entry has actually moved, it is the
        # biggest file in the cache after the thumbnails
        self.texture_cache_file = loads_bytes_io(self.cache_dir / "texture.cache")
        self.__fast_cache_file = None

        changed_textures: dict[str, Texture] = {}
        live: set[str] = set()

        for i, entry in enumerate(self.entries):
            if entry.is_empty:
                continue

            live.add(entry.uuid)

            if entry != self.get(entry.uuid, None):
                changed_textures[entry.uuid] = Texture(
                    index=i,
                    entry=entry,
                    read_head=self.__get_read_head(i, entry),
                    read_thumbnail=self.__get_read_thumbnail(i),
                    body_path=texture_location(self.cache_dir, entry.uuid),
                )

        self.textures = {uuid: texture for uuid, texture in self.textures.items() if uuid in live}
        self.textures |= changed_textures

        return iter(changed_textures.values())

    def watch(self, handler: Callable[[list[Texture]], Any]) -> "BaseObserver":
        """Watch the cache directory for changes and call handler function on updates.

        Requires texture-courier[watchdog] extra to function
        """
        try:
            from watchdog.events import PatternMatchingEventHandler
            from watchdog.observers import Observer
        except ImportError as e:
            raise ImportError(
                'watching a cache needs watchdog extra. install with "pip install texture-courier[watcher]"'
            ) from e

        def on_modified(event: "DirModifiedEvent | FileModifiedEvent") -> None:
            try:
                changed_textures = list(self.refresh())
            except (TextureCacheError, OSError):
                # a viewer part way through rewriting texture.entries leaves it
                # briefly inconsistent. letting that out kills the thread the
                # observer dispatches on and the watch goes deaf for good
                return

            if changed_textures:
                handler(changed_textures)

        event_handler = PatternMatchingEventHandler(patterns=["texture.entries"])
        event_handler.on_modified = on_modified  # type: ignore[method-assign]

        observer = Observer()
        observer.schedule(event_handler, str(self.cache_dir.resolve()))
        observer.start()

        return observer

    def get(self, uuid: str, default: T | None = None) -> Texture | T:
        return self.textures.get(uuid, default)  # type: ignore
