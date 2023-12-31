import argparse
from pathlib import Path
import sys
from typing import Literal
from tqdm import tqdm

from .signal import interrupthandler
from .api import Texture, TextureCache
from .find import find_texturecache, list_texture_caches

OutputMode = Literal["progress", "files", "debug"]


class TextureEmptyError(Exception):
    pass


class Args(argparse.Namespace):
    cache_dir: Path | None
    output_dir: Path
    output_mode: OutputMode
    force: bool
    raw: bool


def prompt_for_cache_dir() -> Path:
    try:
        caches = list_texture_caches()
    except FileNotFoundError:
        print("error: no cache found")
        print('try specificying a cache directory with "texture-courier <cache_dir>"')
        sys.exit(1)

    print("no cache directory specified, enter path or select from the following")
    print("")

    for i, path in enumerate(caches, start=1):
        print(f"{i}: {path.resolve()}")

    print("")

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
        "--watch",
        "-w",
        action="store_true",
        help="watch the cache directory for changes",
        default=False,
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


def save_texture(
    texture: Texture,
    output_dir: Path,
    force: bool,
    raw: bool,
) -> Path:
    if texture.is_empty:
        raise TextureEmptyError

    if raw is False:
        save_path = output_dir / f"{texture.uuid}.jp2"

        if save_path.exists() and not force:
            raise FileExistsError

        # the cache stores textures in a raw jpeg2000 codestream format
        # that is hard for most operating systems to read, which isn't
        # intended to be used for storage. loading it with pillow puts
        # it in a proper container format
        with texture.open_image() as im:
            im.save(save_path)
    else:
        save_path = output_dir / f"{texture.uuid}.j2c"

        if save_path.exists() and not force:
            raise FileExistsError

        save_path.write_bytes(texture.loads())

    return save_path


def end(
    *,
    args: Args,
    good_writes: int,
    existing_textures: int,
    error_write_textures: int,
    empty_textures: int,
) -> None:
    if args.output_mode in ("progress", "debug"):
        print("")
        print(f"wrote {good_writes} textures to {args.output_dir.resolve()}")
        print(
            f"skipped {existing_textures} existing textures"
        ) if existing_textures else None
        print(
            f"{error_write_textures} invalid textures could not be written"
        ) if error_write_textures else None
        print(f"skipped {empty_textures} empty textures") if empty_textures else None


def main() -> None:
    args = parse_args()

    if args.cache_dir:
        cache_dir = find_texturecache(args.cache_dir)

        if cache_dir is None:
            print(f"error: no texture cache found at {args.cache_dir.resolve()}")
            sys.exit(1)
    else:
        if args.output_mode == "files":
            print("error: output mode 'files' requires a cache directory")
            sys.exit(1)

        cache_dir = prompt_for_cache_dir()

    cache = TextureCache(cache_dir)
    empty_textures = 0
    existing_textures = 0
    good_writes = 0
    error_write_textures = 0

    if args.output_mode == "debug":
        print("")
        print("TEXTURE ENTRIES HEADER:")

        for k, v in cache.header:
            print(f"{k}: {v}")

    args.output_dir.mkdir(exist_ok=True)

    if args.watch:

        def handler(modified_textures: list[Texture]) -> None:
            nonlocal existing_textures, good_writes, error_write_textures, empty_textures

            for texture in modified_textures:
                save_path: Path | None = None

                try:
                    save_path = save_texture(
                        texture,
                        output_dir=args.output_dir,
                        force=args.force,
                        raw=args.raw,
                    )
                    good_writes += 1
                except TextureEmptyError:
                    empty_textures += 1
                except FileExistsError:
                    existing_textures += 1
                except OSError:
                    error_write_textures += 1

                if args.output_mode == "progress":
                    printstr = [f"{good_writes} textures extracted"]

                    if error_write_textures:
                        printstr.append(f"{error_write_textures} incomplete textures")

                    if existing_textures:
                        printstr.append(
                            f"{existing_textures} existing textures skipped"
                        )

                    if empty_textures:
                        printstr.append(f"{empty_textures} empty textures skipped")

                    print(", ".join(printstr), end="\r")

                if args.output_mode in ("files", "debug") and save_path:
                    print(save_path.resolve())

        observer = cache.watch(handler)

        if args.output_mode in ("progress", "debug"):
            print("watching for changes in texture cache, press ctrl+c to stop")
            print("")

        with interrupthandler() as h:
            try:
                while observer.is_alive() and not h.interrupted:
                    observer.join(1)
            except KeyboardInterrupt:
                pass
            finally:
                observer.stop()
                observer.join()

            end(
                args=args,
                good_writes=good_writes,
                existing_textures=existing_textures,
                error_write_textures=error_write_textures,
                empty_textures=empty_textures,
            )

            sys.exit(130)

    else:
        with interrupthandler() as h:
            for texture in tqdm(
                cache,
                total=cache.header.entry_count,
                desc="extracting textures",
                unit="tex",
                delay=1,
                disable=args.output_mode != "progress",
            ):
                if h.interrupted:
                    # break the loop if the user presses ctrl+c
                    break

                try:
                    save_path = save_texture(
                        texture,
                        output_dir=args.output_dir,
                        force=args.force,
                        raw=args.raw,
                    )
                    good_writes += 1

                    if args.output_mode in ("files", "debug"):
                        print(save_path.resolve())

                except TextureEmptyError:
                    empty_textures += 1
                except FileExistsError:
                    existing_textures += 1
                except OSError:
                    error_write_textures += 1

            end(
                args=args,
                good_writes=good_writes,
                existing_textures=existing_textures,
                error_write_textures=error_write_textures,
                empty_textures=empty_textures,
            )

            if h.interrupted:
                sys.exit(130)

            if args.output_mode == "files" and good_writes == 0:
                print("warning: no textures were written")
                sys.exit(73)
