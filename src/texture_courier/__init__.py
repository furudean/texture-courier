from typing import Any

from .api import Texture, TextureCache
from .core import Entry, Header, TextureCacheError
from .find import list_texture_caches
from .watch import Watch

__all__ = [
    "Entry",
    "Header",
    "Texture",
    "TextureCache",
    "TextureCacheError",
    "Watch",
    "encode",
    "list_texture_caches",
]


def __getattr__(name: str) -> Any:
    if name == "main":
        from .cli import main

        return main

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
