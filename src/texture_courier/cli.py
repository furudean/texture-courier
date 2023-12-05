import argparse
from pathlib import Path
from typing import Literal
from tqdm import tqdm

from .api import Texture, TextureCache
from .find import find_texturecache, list_texture_cache


def prompt_for_cache_dir() -> Path:
    try:
        caches = list_texture_cache()
    except FileNotFoundError:
        print("error: no cache found")
        print('try specificying a cache directory with "texture-courier <cache_dir>"')
        exit(1)

    if len(caches) == 1:
        print(f"using cache at {caches[0].resolve()}")
        return caches[0]

    print("no cache directory specified, enter path or select from the following")
    print("")

    for i, path in enumerate(caches, start=1):
        print(f"{i}: {path.resolve()}")

    print("")

    while True:
        selection = input("enter path or selection: ")

        if selection.strip() == "":
            continue

        if selection in ("q", "quit", "exit", "0"):
            exit(0)

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
                exit(1)

            return cache


class Args(argparse.Namespace):
    cache_dir: Path | None
    output_dir: Path
    output_mode: Literal["progress", "files", "debug"]
    force: bool
    raw: bool


def parse_args() -> Args:
    parser = argparse.ArgumentParser(
        prog="texture-courier",
        description="rips texture cache from second life viewers",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "cache_dir", type=Path, nargs="?", help="path to texture cache directory"
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help="path to output extracted textures",
        default="./texturecache",
    )

    parser.add_argument(
        "--output-mode",
        "-O",
        choices=("progress", "files", "debug"),
        help="specify output mode. 'progress' shows a progress bar, 'files' prints the path of each file",
        default="progress",
    )

    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="overwrite output files",
        default=False,
    )

    parser.add_argument(
        "--raw",
        action="store_true",
        help="skip encoding and just save the raw codestream",
        default=False,
    )

    args = Args()
    parser.parse_args(namespace=args)

    return args


def main() -> None:
    args = parse_args()

    if args.cache_dir:
        cache_dir = find_texturecache(args.cache_dir)

        if cache_dir is None:
            print(f"error: no texture cache found at {args.cache_dir.resolve()}")
            exit(1)
    else:
        if args.output_mode == "files":
            print("error: output mode 'files' requires a cache directory")
            exit(1)

        cache_dir = prompt_for_cache_dir()

    cache = TextureCache(cache_dir)
    existing_textures = 0
    good_writes = 0
    error_write_textures: list[Texture] = []

    if args.output_mode == "debug":
        print("")
        print("TEXTURE ENTRIES HEADER:")

        for k, v in cache.header.items():
            print(f"{k}: {v}")

    args.output_dir.mkdir(exist_ok=True)

    for texture in tqdm(
        cache,
        total=cache.header["entry_count"],
        desc="extracting textures",
        unit="tex",
        delay=1,
        disable=args.output_mode != "progress",
    ):
        if texture.is_empty:
            continue

        if args.raw is False:
            save_path = args.output_dir / f"{texture.uuid}.jp2"

            if save_path.exists() and not args.force:
                existing_textures += 1
                continue

            try:
                # the cache stores textures in a raw jpeg2000 codestream format
                # that is hard for most operating systems to read, which isn't
                # intended to be used for storage. loading it with pillow puts
                # it in a proper container format
                with texture.open_image() as im:
                    im.save(save_path)
            except OSError:
                error_write_textures.append(texture)
                continue
        else:
            save_path = args.output_dir / f"{texture.uuid}.j2c"

            if save_path.exists() and not args.force:
                existing_textures += 1
                continue

            save_path.write_bytes(texture.loads())

        if args.output_mode in ("files", "debug"):
            print(save_path.resolve())

        good_writes += 1

    if args.output_mode in ("progress", "debug"):
        empty_textures = [texture for texture in cache if texture.is_empty]

        print("")
        print(f"wrote {good_writes} textures to {args.output_dir.resolve()}")
        print(
            f"skipped {existing_textures} existing textures"
        ) if existing_textures else None
        print(
            f"{len(error_write_textures)} invalid textures could not be written"
        ) if error_write_textures else None
        print(
            f"skipped {len(empty_textures)} empty textures"
        ) if empty_textures else None

    if args.output_mode == "files" and good_writes == 0:
        print("error: no textures were written")
        exit(1)
