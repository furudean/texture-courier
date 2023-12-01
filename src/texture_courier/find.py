from pathlib import Path
import itertools

os_cache_roots = [
    # posix
    Path.home(),
    # windows
    Path("%LocaleAppData%"),
    # mac
    Path.home() / "Library/Caches",
]

# macos and windows name their viewer directories the same, but posix has different names
viewer_dirs_posix = [".firestorm_x64/cache", ".alchemynext/cache"]
viewer_dirs_macos_win = ["SecondLife", "Firestorm_x64", "AlchemyNext"]
viewer_dirs = viewer_dirs_posix + viewer_dirs_macos_win


def find_texturecache(path: Path) -> Path | None:
    if not path.exists():
        return None

    # if we find a texture.entries file, we're done
    if path.name == "texturecache" and (path / "texture.entries").exists():
        return path

    # otherwise, recurse into the children with some possible names
    for child in path.iterdir():
        if child.is_dir() and child.name == "texturecache":
            return find_texturecache(child)

    return None


def list_texture_cache() -> list[Path]:
    valid_cache_roots = [path for path in os_cache_roots if path.exists()]

    # find all the possible combinations of cache root and viewer dirs
    viewer_caches = [
        Path.joinpath(root, path)
        for root, path in itertools.product(valid_cache_roots, viewer_dirs)
        if Path.joinpath(root, path).exists()
    ]

    # find the texture cache folder
    texturecaches = [find_texturecache(path) for path in viewer_caches]

    # filter out the paths that don't exist
    texturecaches_non_null = [cache for cache in texturecaches if cache is not None]

    if texturecaches_non_null:
        return texturecaches_non_null
    else:
        raise FileNotFoundError("could not find texture cache")
