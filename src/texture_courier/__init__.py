import sys
from .cli import main
from .api import TextureCache, Texture  # noqa
from .find import list_texture_cache  # noqa


def _sigint_handler(signum, frame):
    exit(130)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
