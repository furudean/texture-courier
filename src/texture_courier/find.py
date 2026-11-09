import itertools
import os
from pathlib import Path

# pathlib does no environment expansion, so %LocalAppData% has to be looked up
local_appdata = os.environ.get("LOCALAPPDATA")

# the xdg spec says to ignore $XDG_CACHE_HOME unless it is absolute
xdg_cache_home = os.environ.get("XDG_CACHE_HOME", "")
xdg_cache = Path(xdg_cache_home) if os.path.isabs(xdg_cache_home) else Path.home() / ".cache"

macos_win_roots = [
    Path.home() / "Library/Caches",
    *([Path(local_appdata)] if local_appdata else []),
]

# macos and windows name their viewer directories the same, but posix has different names
viewer_dirs_posix = [
    ".secondlife/cache",
    ".firestorm_x64/cache",
    ".firestormos_x64/cache",  # firestorm for opensim
    ".alchemynext/cache",  # older alchemy
    ".megapahit/cache",
    ".blackdragon/cache",
    ".catznip/cache",
]

viewer_dirs_xdg = [
    "alchemynext",  # newer alchemy
]

viewer_dirs_macos_win = [
    "SecondLife",
    "Firestorm_x64",
    "FirestormOS_x64",  # firestorm for opensim
    "AlchemyNext",
    "AlchemyViewer",
    "Megapahit",
    "Black Dragon",
    "Catznip64",
    "Catznip",
]

search_paths = [
    *itertools.product(macos_win_roots, viewer_dirs_macos_win),
    *itertools.product([Path.home()], viewer_dirs_posix),
    *itertools.product([xdg_cache], viewer_dirs_xdg),
]


def find_texturecache(path: Path) -> Path | None:
    if not path.is_dir():
        return None

    # a texture.entries file means we've found a hit
    if (path / "texture.entries").is_file():
        return path

    # otherwise, recurse into the children with some possible names. windows
    # and linux keep the cache one level further down, under "cache"
    for name in ("texturecache", "cache"):
        found = find_texturecache(path / name)

        # keep looking through the other children rather than giving up
        if found is not None:
            return found

    return None


def list_texture_caches() -> list[Path]:
    """Best-effort list of the system's possible texture caches"""
    viewer_caches = [root / path for root, path in search_paths if (root / path).exists()]

    # find the texture cache folder
    texturecaches = [find_texturecache(path) for path in viewer_caches]

    # case-insensitive filesystems can reach one cache by two spellings, like
    # AlchemyNext and alchemynext when $XDG_CACHE_HOME is ~/Library/Caches
    unique: dict[tuple[int, int], Path] = {}

    for cache in filter(None, texturecaches):
        stat = cache.stat()
        unique.setdefault((stat.st_dev, stat.st_ino), cache)

    if unique:
        return list(unique.values())
    else:
        raise FileNotFoundError("could not find texture cache")
