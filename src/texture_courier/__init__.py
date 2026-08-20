import sys

from .api import Texture, TextureCache
from .cli import main
from .core import Entry, Header
from .find import list_texture_caches

__all__ = [
    "Entry",
    "Header",
    "Texture",
    "TextureCache",
    "list_texture_caches",
    "main",
]

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit(130)
