from io import BytesIO
from pathlib import Path
from typing import Callable, Iterator, Optional
from typing_extensions import TypeVar
from datetime import datetime

from . import core

from PIL import Image

T = TypeVar("T", default=None)


def loads_bytes_io(p: Path) -> BytesIO:
    return BytesIO(p.read_bytes())


def format_bytes(size: float) -> str:
    power = 2**10
    n = 0
    power_labels = {0: "bytes", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}

    while size > power:
        size /= power
        n += 1

    return f"{int(size)} {power_labels[n]}"


class Texture:
    index: int
    loads: Callable[[], bytes]
    """Open texture as a bytes object"""

    uuid: str
    image_size: int
    body_size: int
    time: datetime

    def __init__(self, *, index: int, entry: core.Entry, loads: Callable[[], bytes]):
        self.index = index
        self.loads = loads

        for key, value in entry.items():
            setattr(self, key, value)

    def __repr__(self) -> str:
        size = format_bytes(self.image_size) if self.is_empty else "empty"
        return f"<Texture {self.uuid}, {self.time}, {size}>"

    @property
    def is_empty(self) -> bool:
        return self.image_size <= 0

    def open_image(self) -> Image.Image:
        """Open texture as a pillow image"""

        b = self.loads()
        return Image.open(BytesIO(b), formats=["jpeg2000"])


class TextureCache:
    cache_dir: Path
    texture_entries_file: BytesIO
    texture_cache_file: BytesIO

    header: core.Header
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

    def __repr__(self) -> str:
        total_size = sum(texture.image_size for texture in self)

        return (
            f"<TextureCache {self.cache_dir.resolve()}, "
            f"{self.header['entry_count']} entries, "
            f"{format_bytes(total_size)}>"
        )

    def __get_read_bytes(self, i: int, entry: core.Entry) -> Callable[[], bytes]:
        def read_bytes() -> bytes:
            head = core.read_texture_cache(self.texture_cache_file, i)

            if entry["image_size"] <= 601 and entry["body_size"] == 0:
                # sometimes the file is smaller than 600 bytes, so using the head is
                # sufficient
                return head
            else:
                body = core.read_texture_body(entry["uuid"], cache_dir=self.cache_dir)

                return head + body

        return read_bytes

    def refresh(self) -> None:
        self.texture_entries_file = loads_bytes_io(self.cache_dir / "texture.entries")
        self.texture_cache_file = loads_bytes_io(self.cache_dir / "texture.cache")

        self.header = core.decode_texture_entries_header(self.texture_entries_file)

        entries = core.decode_texture_entries(
            self.texture_entries_file, entry_count=self.header["entry_count"]
        )

        for i, entry in enumerate(entries):
            if not entry["uuid"] in self.textures:
                self.textures[entry["uuid"]] = Texture(
                    index=i,
                    entry=entry,
                    loads=self.__get_read_bytes(i, entry),
                )

    def get(self, uuid: str, default: Optional[T] = None) -> Texture | T:
        return self.textures.get(uuid, default)  # type: ignore
