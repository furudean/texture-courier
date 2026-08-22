from typing import TYPE_CHECKING, Any

from .api import Texture, TextureCache
from .core import Entry, Header
from .find import list_texture_caches

if TYPE_CHECKING:
    from .cli import main

__all__ = [
    "Entry",
    "Header",
    "Texture",
    "TextureCache",
    "list_texture_caches",
    "main",
]


def __getattr__(name: str) -> Any:
    if name == "main":
        from .cli import main

        return main

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
