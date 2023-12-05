import sys
from .cli import main
from .api import TextureCache, Texture  # noqa
from .find import list_texture_cache  # noqa


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
