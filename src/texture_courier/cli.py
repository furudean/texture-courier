import argparse
import os
import sys
from pathlib import Path

from .api import Texture, TextureCache
from .error import TextureCacheError
from .find import find_texturecache, list_texture_caches
from .signal import interrupthandler


class TextureError(Exception):
    pass


class TextureEmptyError(TextureError):
    pass


class TextureIncompleteError(TextureError):
    pass


class Args(argparse.Namespace):
    cache_dir: Path | None
    output_dir: Path
    debug: bool
    quiet: bool
    force: bool
    raw: bool
    skip_integrity: bool
    thumb: bool


def prompt_for_cache_dir() -> Path:
    try:
        caches = list_texture_caches()
    except FileNotFoundError:
        print("error: no cache found")
        print('try specifying a cache directory with "texture-courier <cache_dir>"')
        sys.exit(1)

    print("no cache directory specified, enter path or select from the following")
    print()

    for i, path in enumerate(caches, start=1):
        print(f"{i}: {path.resolve()}")

    print()

    with interrupthandler(immediate=True) as h:
        while not h.interrupted:
            selection = input("enter path or selection: ")

            if selection.strip() == "":
                continue

            if selection in ("q", "quit", "exit", "0"):
                sys.exit(0)

            if selection.isdigit():
                s = int(selection)

                if s < 1 or s > len(caches):
                    print("invalid selection")
                    continue

                return caches[s - 1]
            else:
                cache = find_texturecache(Path(selection))

                if cache is None:
                    print(f"error: no texture cache found at {selection}")
                    sys.exit(1)

                return cache

    assert False, "unreachable"


def parse_args() -> Args:
    parser = argparse.ArgumentParser(
        prog="texture-courier",
        description="rips texture cache from second life viewers",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("cache_dir", type=Path, nargs="?", help="path to texture cache directory")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help="path to output extracted textures",
        default="./texturecache",
    )

    verbosity = parser.add_mutually_exclusive_group()

    verbosity.add_argument(
        "--debug",
        action="store_true",
        help="show debug logging",
        default=False,
    )

    verbosity.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="don't print anything",
        default=False,
    )

    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="overwrite output files",
        default=False,
    )

    output_format = parser.add_mutually_exclusive_group()

    output_format.add_argument(
        "--raw",
        action="store_true",
        help="skip encoding and just save the raw codestream",
        default=False,
    )

    parser.add_argument(
        "--skip-integrity",
        action="store_true",
        help="skip integrity checks",
        default=False,
    )

    output_format.add_argument(
        "--thumb",
        action="store_true",
        help="dump thumbnails instead of textures. these are tiny, but exist for partial downloads.",
        default=False,
    )

    args = Args()
    parser.parse_args(namespace=args)

    return args


def save_texture(texture: Texture, output_dir: Path, args: Args) -> Path:
    if texture.is_empty:
        raise TextureEmptyError

    save_path = output_dir / f"{texture.uuid}.{'j2c' if args.raw else 'jp2'}"

    if save_path.exists() and not args.force:
        raise FileExistsError

    verify = not args.skip_integrity

    try:
        if args.raw:
            b = texture.codestream(verify=verify)
        else:
            b = texture.jpeg_2000(verify=verify)
    except TextureCacheError as e:
        raise TextureIncompleteError(str(e)) from e

    save_path.write_bytes(b)

    # stamp last access and modification times to the same as the date in cache
    os.utime(save_path, (texture.time.timestamp(), texture.time.timestamp()))

    return save_path


def save_thumbnail(texture: Texture, output_dir: Path, args: Args) -> Path:
    if texture.is_empty:
        raise TextureEmptyError

    save_path = output_dir / f"{texture.uuid}.png"

    if save_path.exists() and not args.force:
        raise FileExistsError

    thumbnail = texture.thumbnail

    if thumbnail is None:
        raise TextureEmptyError

    save_path.write_bytes(thumbnail.png())

    os.utime(save_path, (texture.time.timestamp(), texture.time.timestamp()))

    return save_path


def end(
    *,
    args: Args,
    good_writes: int,
    existing_textures: int,
    incomplete_textures: int,
    error_write_textures: int,
    empty_textures: int,
) -> None:
    s = [f"wrote {good_writes:,} textures to {args.output_dir.resolve()}"]

    if existing_textures:
        s.append(f"skipped {existing_textures:,} existing textures")

    if incomplete_textures:
        s.append(f"skipped {incomplete_textures:,} incomplete textures")
    if error_write_textures:
        s.append(f"{error_write_textures:,} incomplete/invalid textures not saved")

    if empty_textures:
        s.append(f"skipped {empty_textures:,} empty textures")

    print()
    for line in s:
        print(line)


def main() -> None:
    args = parse_args()

    if args.cache_dir:
        cache_dir = find_texturecache(args.cache_dir)

        if cache_dir is None:
            print(f"error: no texture cache found at {args.cache_dir.resolve()}")
            sys.exit(1)
    else:
        cache_dir = prompt_for_cache_dir()

    try:
        cache = TextureCache(cache_dir)
    except TextureCacheError as e:
        print(f"error: {e}")
        sys.exit(1)

    good_writes = 0

    if args.debug:
        print()
        print("TEXTURE ENTRIES HEADER:")

        for k, v in cache.header:
            print(f"{k}: {v}")

    args.output_dir.mkdir(exist_ok=True)

    if args.thumb and not cache.has_fastcache:
        print("error: this cache has no FastCache.cache to read thumbnails from")
        sys.exit(1)

    save = save_thumbnail if args.thumb else save_texture

    empty_textures = 0
    error_write_textures = 0
    incomplete_textures = 0
    existing_textures = 0
    total = len(cache)
    progress_width = len(f"{total:,}/{total:,}")

    with interrupthandler() as h:
        for i, texture in enumerate(cache, start=1):
            if h.interrupted:
                break

            if not args.debug and not args.quiet:
                print(f"\r{f'{i:,}/{total:,}':<{progress_width}}", end="", flush=True)

            try:
                save_path = save(texture, output_dir=args.output_dir, args=args)
                good_writes += 1

                if args.debug:
                    print(f"{texture!r} -> {save_path.resolve()}")
            except TextureEmptyError:
                empty_textures += 1

                if args.debug:
                    print(f"{texture!r} skipped, empty")
            except TextureIncompleteError as e:
                incomplete_textures += 1

                if args.debug:
                    print(f"{texture!r} skipped, incomplete: {e}")
            except FileExistsError:
                existing_textures += 1

                if args.debug:
                    print(f"{texture!r} skipped, already exists")
            except Exception as e:  # noqa: BLE001
                error_write_textures += 1

                if args.debug:
                    print(f"{texture!r} failed: {e!r}")

        if not args.debug and not args.quiet:
            print(f"\r{' ' * progress_width}\r", end="")

        if not args.quiet:
            end(
                args=args,
                good_writes=good_writes,
                incomplete_textures=incomplete_textures,
                existing_textures=existing_textures,
                error_write_textures=error_write_textures,
                empty_textures=empty_textures,
            )

        if good_writes == 0:
            print("warning: no textures were written")
            sys.exit(73)
