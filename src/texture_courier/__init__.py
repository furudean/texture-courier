import sys

from .api import Texture, TextureCache  # noqa: F401
from .cli import main
from .core import Entry, Header  # noqa: F401
from .find import list_texture_caches  # noqa: F401

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit(130)
