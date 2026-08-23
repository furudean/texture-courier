import functools
from pathlib import Path

import pytest

from texture_courier.api import Texture, TextureCache
from texture_courier.core import Thumbnail, read_fast_cache
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
        if not texture.whole():
            continue

        components = codestream_size(texture.codestream())[2]
        samples.setdefault(f"{components} components", texture)

    return dict(sorted(samples.items()))


@pytest.fixture(scope="session")
def cache() -> TextureCache:
    return load_cache()


@pytest.fixture(scope="session")
def textures() -> list[Texture]:
    """Every texture the cache claims to hold in full"""
    return [texture for texture in load_cache() if texture.whole()]


@pytest.fixture(scope="session")
def thumbnails() -> list[tuple[Texture, Thumbnail]]:
    """Every thumbnail in the fixture cache, next to the texture it belongs to"""
    cache = load_cache()

    assert cache.fast_cache_file is not None

    pairs = []

    for texture in cache:
        thumbnail = read_fast_cache(cache.fast_cache_file, texture.index)

        if thumbnail is not None:
            pairs.append((texture, thumbnail))

    return pairs
