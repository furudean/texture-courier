import sys

from .cli import main
from .core import Header, Entry  # noqa
from .api import TextureCache, Texture  # noqa
from .find import list_texture_caches  # noqa


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit(130)
