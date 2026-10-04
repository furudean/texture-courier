from collections.abc import Iterator
from functools import cached_property
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import TypeVar, overload

from .core import (
    ENTRY_BYTE_COUNT,
    HEADER_BYTE_COUNT,
    Entry,
    Header,
    Thumbnail,
    decode_texture_entries,
    read_fast_cache,
    read_texture_body,
    read_texture_cache,
    texture_location,
)
from .encode import (
    EOC_MARKER,
    SOC_MARKER,
    jp2_prefix,
    tile_parts_end,
)
from .error import TextureCacheError
from .util import format_bytes

T = TypeVar("T")

DIFF_BLOCK_BYTE_COUNT = 4096

# file bytes and the texture.entries read after them
Snapshot = tuple[bytes, bytes]


class Texture(Entry):
    index: int
    cache_dir: Path

    def __init__(
        self,
        *,
        index: int,
        entry: Entry,
        cache: "TextureCache",
    ):
        self.__dict__.update(entry.__dict__)

        self.index = index
        self.cache_dir = cache.cache_dir
        self.__cache = cache

    @cached_property
    def body_path(self) -> Path:
        return texture_location(self.cache_dir, self.uuid)

    def __repr__(self) -> str:
        size = format_bytes(self.image_size) if not self.is_empty else "empty"

        return f"<Texture {self.uuid}, {self.time}, {size}, whole={self.whole()}>"

    def whole(self) -> bool:
        """Whether the cache claims to have the whole image downloaded

        Only the entry's account of itself, which does not necessarily reflect the actual state on disk.
        """
        return self.is_complete

    def __incomplete(self) -> TextureCacheError:
        return TextureCacheError(f"{self.uuid} holds {self.cached_size} of {self.image_size} bytes")

    def __verify(self, head: bytes, body: bytes) -> None:
        if not self.is_complete:
            raise self.__incomplete()

        if len(head) != self.head_size:
            raise TextureCacheError(f"{self.uuid} has a {len(head)} byte head, entry describes {self.head_size}")

        if len(body) != self.body_size:
            raise TextureCacheError(f"{self.uuid} has a {len(body)} byte body, entry describes {self.body_size}")

        if not head.startswith(SOC_MARKER):
            raise TextureCacheError(f"{self.uuid} does not open on a jpeg 2000 codestream")

        # the marker can straddle the head and a one byte body
        if not (head + body[-2:]).endswith(EOC_MARKER):
            raise TextureCacheError(f"{self.uuid} is missing the marker that ends a codestream")

        # the viewer writes a row before its head, so a head read in between
        # belongs to the row's previous occupant and its lengths will not fit
        end = tile_parts_end(head, body)

        if end is not None and end != len(head) + len(body) - len(EOC_MARKER):
            raise TextureCacheError(f"{self.uuid} has a head whose tile-part lengths do not fit the texture")

    def fs_size(self) -> int:
        """Get the size of the texture file on disk in bytes"""
        if self.is_empty:
            return 0

        try:
            body_size = self.body_path.stat().st_size
        except FileNotFoundError:
            body_size = 0

        return self.head_size + body_size

    def __read_codestream(self, *, verify: bool) -> tuple[bytes, bytes]:
        # sanity check before doing expensive reads
        if verify and not self.is_complete:
            raise self.__incomplete()

        # the slot is a fixed width, so trim the zero padding that follows
        head = self.__cache._read_head(self)[: self.head_size]
        body = b"" if self.body_size == 0 else read_texture_body(self.body_path)

        if verify:
            # against the bytes in hand rather than the file, a viewer writing
            # to the cache can move the body between a check and the read after
            self.__verify(head, body)

        return head, body

    def codestream(self, *, verify: bool = True) -> bytes:
        """
        Open the bare JPEG 2000 codestream as a bytes object.

        This is not intended to be used as a transfer or storage format.
        """

        head, body = self.__read_codestream(verify=verify)

        return head + body

    def jpeg_2000(self, *, verify: bool = True) -> bytes:
        """
        Put the codestream in a proper JPEG 2000 container.

        This format is intended for storage and transfer. Has a very minimal cost compared to the codestream,
        but will have much better compatibility with other software.
        """

        head, body = self.__read_codestream(verify=verify)

        return b"".join((jp2_prefix(head, len(head) + len(body)), head, body))

    @cached_property
    def thumbnail(self) -> Thumbnail | None:
        """The thumbnail the cache keeps beside the texture, if it has one yet"""

        return self.__cache._read_thumbnail(self)

    def dimensions(self) -> tuple[int, int] | None:
        """The dimensions the cache claims for the texture as (width, height)

        This reads the thumbnail into memory.
        """

        thumbnail = self.thumbnail

        return None if thumbnail is None else thumbnail.source_dimensions


class TextureCache:
    cache_dir: Path

    header: Header
    entries: list[Entry]
    textures: dict[str, Texture]

    __entries_raw: bytes
    __snapshots: dict[str, Snapshot]
    __load_lock: Lock
    __order: list[Texture] | None

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.entries = []
        self.textures = {}
        self.__entries_raw = b""
        self.__snapshots = {}
        self.__load_lock = Lock()
        self.__order = None

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

    def __contains__(self, key: object) -> bool:
        if isinstance(key, Entry):
            return self.textures.get(key.uuid) == key

        return isinstance(key, str) and key in self.textures

    def __ordered(self) -> list[Texture]:
        if self.__order is None:
            self.__order = list(self.textures.values())

        return self.__order

    @overload
    def __getitem__(self, key: str | int) -> Texture: ...

    @overload
    def __getitem__(self, key: slice) -> list[Texture]: ...

    def __getitem__(self, key: str | int | slice) -> Texture | list[Texture]:
        if isinstance(key, str):
            return self.textures[key]

        return self.__ordered()[key]

    def __repr__(self) -> str:
        total_size = sum(texture.image_size for texture in self)

        return f"<TextureCache {self.cache_dir.resolve()}, {len(self)} textures, {format_bytes(total_size)}>"

    @property
    def has_fastcache(self) -> bool:
        return (self.cache_dir / "FastCache.cache").is_file()

    def __snapshot(self, name: str) -> Snapshot:
        loaded = self.__snapshots.get(name)

        if loaded is None:
            with self.__load_lock:
                loaded = self.__snapshots.get(name)

                if loaded is None:
                    path = self.cache_dir / name
                    raw = path.read_bytes() if path.is_file() else b""

                    # texture.entries is read after the file it describes, so a
                    # row the viewer reuses between the two reads fails the row check
                    entries_raw = (self.cache_dir / "texture.entries").read_bytes()
                    loaded = self.__snapshots[name] = (raw, entries_raw)

        return loaded

    @staticmethod
    def __check_row(texture: Texture, entries_raw: bytes) -> None:
        offset = HEADER_BYTE_COUNT + texture.index * ENTRY_BYTE_COUNT
        slot = entries_raw[offset : offset + ENTRY_BYTE_COUNT]

        if len(slot) != ENTRY_BYTE_COUNT or Entry.from_bytes(slot) != texture:
            raise TextureCacheError(f"{texture.uuid} has left row {texture.index} since it was read")

    # rows are checked against the entries read alongside the file, since
    # self.entries can predate it
    def __read_slots(self, name: str, texture: Texture) -> bytes:
        raw, entries_raw = self.__snapshot(name)
        self.__check_row(texture, entries_raw)

        return raw

    def _read_head(self, texture: Texture) -> bytes:
        return read_texture_cache(self.__read_slots("texture.cache", texture), texture.index)

    def _read_thumbnail(self, texture: Texture) -> Thumbnail | None:
        fast_cache = self.__read_slots("FastCache.cache", texture)

        return read_fast_cache(fast_cache, texture.index) if fast_cache else None

    def __texture(self, i: int, entry: Entry) -> Texture:
        return Texture(index=i, entry=entry, cache=self)

    def __changed_slots(self, entries_raw: bytes, entry_count: int) -> list[int] | None:
        previous = self.__entries_raw

        # the file can run past the rows the header counts, so only the header
        # tells whether the count has changed
        if previous[:HEADER_BYTE_COUNT] != entries_raw[:HEADER_BYTE_COUNT]:
            return None

        slots: list[int] = []
        rows_end = HEADER_BYTE_COUNT + entry_count * ENTRY_BYTE_COUNT

        for start in range(HEADER_BYTE_COUNT, rows_end, DIFF_BLOCK_BYTE_COUNT):
            stop = min(start + DIFF_BLOCK_BYTE_COUNT, rows_end)

            if previous[start:stop] == entries_raw[start:stop]:
                continue

            first = (start - HEADER_BYTE_COUNT) // ENTRY_BYTE_COUNT
            last = (stop - HEADER_BYTE_COUNT - 1) // ENTRY_BYTE_COUNT

            # a slot that straddles a block boundary falls in both halves
            if slots:
                first = max(first, slots[-1] + 1)

            for i in range(first, last + 1):
                offset = HEADER_BYTE_COUNT + i * ENTRY_BYTE_COUNT

                if previous[offset : offset + ENTRY_BYTE_COUNT] != entries_raw[offset : offset + ENTRY_BYTE_COUNT]:
                    slots.append(i)

        return slots

    def refresh(self) -> Iterator[Texture]:
        entries_raw = (self.cache_dir / "texture.entries").read_bytes()

        if entries_raw == self.__entries_raw:
            return iter(())

        texture_entries_file = BytesIO(entries_raw)
        header = Header.from_texture_entries(texture_entries_file)
        slots = self.__changed_slots(entries_raw, header.entry_count)

        changed_textures: dict[str, Texture] = {}
        evicted: set[str] = set()

        if slots is None:
            entries = decode_texture_entries(
                texture_entries_file,
                entry_count=header.entry_count,
            )
            live: set[str] = set()

            for i, entry in enumerate(entries):
                if entry.is_empty:
                    continue

                live.add(entry.uuid)
                existing = self.textures.get(entry.uuid)

                # an entry equal by its fields can still have changed rows
                if existing is None or existing.index != i or existing != entry:
                    changed_textures[entry.uuid] = self.__texture(i, entry)

            evicted = self.textures.keys() - live
        else:
            entries = list(self.entries)

            for i in slots:
                offset = HEADER_BYTE_COUNT + i * ENTRY_BYTE_COUNT
                stale = entries[i]
                entry = Entry.from_bytes(entries_raw[offset : offset + ENTRY_BYTE_COUNT])
                entries[i] = entry

                # the row's old occupant only goes if it has not since turned
                # up in a row of its own
                texture = self.textures.get(stale.uuid)

                if texture is not None and texture.index == i:
                    evicted.add(stale.uuid)

                if not entry.is_empty:
                    changed_textures[entry.uuid] = self.__texture(i, entry)

        evicted -= changed_textures.keys()
        textures = (
            {uuid: texture for uuid, texture in self.textures.items() if uuid not in evicted}
            if evicted
            else dict(self.textures)
        )
        textures |= changed_textures

        # a load in flight would otherwise store bytes from before the refresh
        with self.__load_lock:
            self.__entries_raw = entries_raw
            self.__snapshots = {}
            self.header = header
            self.entries = entries
            self.textures = textures
            self.__order = None

        return iter(changed_textures.values())

    @overload
    def get(self, uuid: str) -> Texture | None: ...

    @overload
    def get(self, uuid: str, default: Texture) -> Texture: ...

    @overload
    def get(self, uuid: str, default: T) -> Texture | T: ...

    def get(self, uuid: str, default: T | None = None) -> Texture | T | None:
        return self.textures.get(uuid, default)
