import functools
from pathlib import Path

import pytest

from texture_courier.api import Texture, TextureCache
from texture_courier.core import Thumbnail
from texture_courier.encode import codestream_size

CACHE_DIR = Path(__file__).parent.parent / "fixtures" / "texturecache"

# the corpus tests are the only ones that need a cache to read
collect_ignore: list[str] = [] if CACHE_DIR.is_dir() else ["test_corpus.py"]


@functools.cache
def load_cache() -> TextureCache:
    return TextureCache(CACHE_DIR)


def sample_textures() -> dict[str, Texture]:
    samples: dict[str, Texture] = {}

    for texture in load_cache():
        if not texture.is_downloaded():
            continue

        components = codestream_size(texture.loads())[2]
        samples.setdefault(f"{components} components", texture)

    return dict(sorted(samples.items()))


@pytest.fixture(scope="session")
def cache() -> TextureCache:
    return load_cache()


@pytest.fixture(scope="session")
def textures() -> list[Texture]:
    """Every texture the fixture cache holds in one piece"""
    return [texture for texture in load_cache() if texture.is_downloaded()]


@pytest.fixture(scope="session")
def thumbnails() -> list[tuple[Texture, Thumbnail]]:
    """Every thumbnail in the fixture cache, next to the texture it belongs to"""
    pairs = []

    for texture in load_cache():
        thumbnail = texture.loads_thumbnail()

        if thumbnail is not None:
            pairs.append((texture, thumbnail))

    return pairs
