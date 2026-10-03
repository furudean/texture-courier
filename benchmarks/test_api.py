import random
import shutil
import struct
import tempfile
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from texture_courier import Texture, TextureCache
from texture_courier.core import ENTRY_BYTE_COUNT, HEADER_BYTE_COUNT
from texture_courier.encode import wrap_jp2
from texture_courier.error import TextureCacheError

ROUNDS = 10

# uuid, image size and body size come before the time in an entry
ENTRY_TIME_OFFSET = struct.calcsize("16sii")
CHANGED_ENTRY_COUNT = 10

SCRATCH = tempfile.TemporaryDirectory()


def open_cache(cache_dir: Path) -> Callable[[], Any]:
    return lambda: TextureCache(cache_dir)


def one_thumbnail(cache_dir: Path) -> Callable[[], Any]:
    cache = TextureCache(cache_dir)
    texture = cache[len(cache) // 2]

    return lambda: texture.thumbnail


def thumbnails(textures: list[Texture]) -> Callable[[], Any]:
    return lambda: [texture.thumbnail for texture in textures]


def thumbnails_in_order(cache_dir: Path) -> Callable[[], Any]:
    return thumbnails(list(TextureCache(cache_dir)))


def thumbnails_shuffled(cache_dir: Path) -> Callable[[], Any]:
    textures = list(TextureCache(cache_dir))
    random.Random(0).shuffle(textures)

    return thumbnails(textures)


def codestreams(cache_dir: Path) -> Callable[[], Any]:
    textures = [texture for texture in TextureCache(cache_dir) if texture.whole()]

    def run() -> None:
        for texture in textures:
            try:
                texture.codestream()
            except (TextureCacheError, FileNotFoundError):
                pass

    return run


def thumbnail_pngs(cache_dir: Path) -> Callable[[], Any]:
    thumbnails = (texture.thumbnail for texture in TextureCache(cache_dir))
    present = [thumbnail for thumbnail in thumbnails if thumbnail is not None]

    return lambda: [thumbnail.png() for thumbnail in present]


def jp2_wraps(cache_dir: Path) -> Callable[[], Any]:
    streams = []

    for texture in TextureCache(cache_dir):
        if not texture.whole():
            continue

        try:
            streams.append(texture.codestream())
        except (TextureCacheError, FileNotFoundError):
            pass

    def run() -> None:
        for codestream in streams:
            try:
                wrap_jp2(codestream)
            except TextureCacheError:
                pass

    return run


def mirror(cache_dir: Path) -> Path:
    """A cache with its own texture.entries, sharing everything else with cache_dir"""
    mirror_dir = Path(SCRATCH.name) / "mirror"

    shutil.rmtree(mirror_dir, ignore_errors=True)
    mirror_dir.mkdir()

    for path in cache_dir.absolute().iterdir():
        if path.name == "texture.entries":
            shutil.copyfile(path, mirror_dir / path.name)
        else:
            (mirror_dir / path.name).symlink_to(path)

    return mirror_dir


def changed_cache(cache_dir: Path) -> TextureCache:
    """A cache whose texture.entries has moved on since it was opened"""
    cache = TextureCache(mirror(cache_dir))
    textures = list(cache)
    entries_path = cache.cache_dir / "texture.entries"
    raw = bytearray(entries_path.read_bytes())

    # a viewer bumps the time of an entry it reads, so this spreads a few of
    # those across the file
    for texture in textures[:: max(1, len(textures) // CHANGED_ENTRY_COUNT)][:CHANGED_ENTRY_COUNT]:
        offset = HEADER_BYTE_COUNT + texture.index * ENTRY_BYTE_COUNT + ENTRY_TIME_OFFSET
        struct.pack_into("I", raw, offset, int(texture.time.timestamp()) + 1)

    entries_path.write_bytes(raw)

    return cache


def refresh(cache_dir: Path) -> Callable[[], Any]:
    return changed_cache(cache_dir).refresh


def refresh_then_thumbnail(cache_dir: Path) -> Callable[[], Any]:
    cache = changed_cache(cache_dir)

    return lambda: next(cache.refresh()).thumbnail


WORKLOADS: dict[str, Callable[[Path], Callable[[], Any]]] = {
    "open": open_cache,
    "one thumbnail": one_thumbnail,
    "thumbnails in order": thumbnails_in_order,
    "thumbnails shuffled": thumbnails_shuffled,
    "codestreams": codestreams,
    "thumbnail pngs": thumbnail_pngs,
    "jp2 wraps": jp2_wraps,
    "refresh": refresh,
    "refresh then thumbnail": refresh_then_thumbnail,
}


@pytest.mark.parametrize("name", WORKLOADS)
def test_time(benchmark: BenchmarkFixture, cache_dir: Path, name: str) -> None:
    workload = WORKLOADS[name]

    benchmark.pedantic(  # type: ignore[no-untyped-call]
        lambda run: run(),
        setup=lambda: ((workload(cache_dir),), {}),
        rounds=ROUNDS,
    )


@pytest.mark.parametrize("name", WORKLOADS)
def test_memory(cache_dir: Path, name: str, record_memory: Callable[[str, int, int], None]) -> None:
    run = WORKLOADS[name](cache_dir)

    tracemalloc.start()

    try:
        result = run()
        held, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    del result
    record_memory(name, peak, held)
