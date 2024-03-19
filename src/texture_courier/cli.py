import argparse
from pathlib import Path
import sys
from typing import Literal
from tqdm import tqdm
import os

from .signal import interrupthandler
from .api import Texture, TextureCache
from .find import find_texturecache, list_texture_caches

OutputMode = Literal["progress", "files", "debug"]


class TextureError(Exception):
    pass


class TextureEmptyError(TextureError):
    pass


class TextureIncompleteError(TextureError):
    pass


class Args(argparse.Namespace):
    cache_dir: Path | None
    output_dir: Path
    output_mode: OutputMode
    force: bool
    raw: bool
    skip_integrity: bool


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


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

    parser.add_argument(
        "--skip-integrity",
        action="store_true",
        help="skip integrity checks",
        default=False,
    )

    args = Args()
    parser.parse_args(namespace=args)

    return args


def save_texture(texture: Texture, output_dir: Path, args: Args) -> Path:
    if texture.is_empty:
        raise TextureEmptyError

    if texture.is_downloaded() is False and not args.skip_integrity:
        raise TextureIncompleteError

    if args.raw is False:
        save_path = output_dir / f"{texture.uuid}.jp2"

        if save_path.exists() and not args.force:
            raise FileExistsError

        # the cache stores textures in a raw jpeg2000 codestream format
        # that is hard for most operating systems to read, which isn't
        # intended to be used for storage. loading it with pillow puts
        # it in a proper container format
        with texture.open_image() as im:
            im.save(save_path)
    else:
        save_path = output_dir / f"{texture.uuid}.j2c"

        if save_path.exists() and not args.force:
            raise FileExistsError

        save_path.write_bytes(texture.loads())

    # set last access and modification times to the same as the date in cache
    # (atime, mtime)
    os.utime(save_path, (texture.time.timestamp(), texture.time.timestamp()))

    return save_path


def print_text_frame(string_lst: list[str], width: int | None = None) -> None:
    if width is None:
        width = max(len(line) for line in string_lst) + 4

    g_line = "+{0}+".format("-"*(width-2))
    print(g_line)
    for line in string_lst:
        print("| {0:<{1}} |".format(line, width-4))
    print(g_line)


def end(
    *,
    args: Args,
    good_writes: int,
    existing_textures: int,
    incomplete_textures: int,
    error_write_textures: int,
    empty_textures: int,
) -> None:
    if args.output_mode in ("progress", "debug"):
        s = [f"wrote {good_writes} textures to {args.output_dir.resolve()}"]

        if existing_textures:
            s.append(f"skipped {existing_textures} existing textures")

        if incomplete_textures:
            s.append(f"skipped {incomplete_textures} incomplete textures")
        if error_write_textures:
            s.append(f"{error_write_textures} incomplete/invalid textures not saved")

        if empty_textures:
            s.append(f"skipped {empty_textures} empty textures")

        print("\n")
        print_text_frame(s)


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
    good_writes = 0

    if args.output_mode == "debug":
        print("")
        print("TEXTURE ENTRIES HEADER:")

        for k, v in cache.header:
            print(f"{k}: {v}")

    args.output_dir.mkdir(exist_ok=True)

    if args.watch:
        incomplete_stack: set[str] = set()
        failed_stack: set[str] = set()
        empty_stack: set[str] = set()
        existing_stack: set[str] = set()

        def handler(modified_textures: list[Texture]) -> None:
            nonlocal good_writes

            for texture in modified_textures:
                save_path: Path | None = None

                try:
                    save_path = save_texture(
                        texture,
                        output_dir=args.output_dir,
                        args=args,
                    )

                    good_writes += 1
                    empty_stack.discard(texture.uuid)
                    failed_stack.discard(texture.uuid)
                    incomplete_stack.discard(texture.uuid)
                except TextureEmptyError:
                    empty_stack.add(texture.uuid)
                except FileExistsError:
                    existing_stack.add(texture.uuid)
                    failed_stack.discard(texture.uuid)
                except TextureIncompleteError:
                    incomplete_stack.add(texture.uuid)
                except OSError as e:
                    failed_stack.add(texture.uuid)

                    if args.output_mode == "debug":
                        print(f"error writing {texture.uuid}: {e}")

                if args.output_mode == "progress":
                    printstr = [f"{good_writes} textures extracted"]

                    if len(incomplete_stack):
                        printstr.append(f"{len(incomplete_stack)} incomplete")

                    if len(failed_stack):
                        printstr.append(f"{len(failed_stack)} incomplete/failed")

                    if len(existing_stack):
                        printstr.append(f"{len(existing_stack)} existing skipped")

                    if len(empty_stack):
                        printstr.append(f"{len(empty_stack)} empty skipped")

                    print(", ".join(printstr), end="\r", flush=True)

                if args.output_mode in ("files", "debug") and save_path:
                    print(save_path.resolve())

        observer = cache.watch(handler)

        clear_screen()

        if args.output_mode in ("progress", "debug"):
            print(f"watching for changes in {cache.cache_dir.resolve()}")
            print(f"extracting to {args.output_dir.resolve()}")
            print("")
            print("input ctrl+c or ctrl+d to stop")
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
                existing_textures=len(existing_stack),
                incomplete_textures=len(incomplete_stack),
                error_write_textures=len(failed_stack),
                empty_textures=len(empty_stack),
            )

            sys.exit(130)

    else:
        empty_textures = 0
        error_write_textures = 0
        incomplete_textures = 0
        existing_textures = 0

    with interrupthandler() as h:
        with tqdm(
            total=cache.header.entry_count,
            desc="extracting textures",
            unit="tex",
            delay=1,
            disable=args.output_mode != "progress",
        ) as progress:
            for texture in cache:
                if h.interrupted:
                    progress.close()
                    break

                try:
                    save_path = save_texture(texture, output_dir=args.output_dir, args=args)
                    good_writes += 1

                    if args.output_mode in ("files", "debug"):
                        print(save_path.resolve())
                except TextureEmptyError:
                    empty_textures += 1
                except TextureIncompleteError:
                    incomplete_textures += 1
                except FileExistsError:
                    existing_textures += 1
                except Exception:
                    error_write_textures += 1

                postfix = {
                    "ok": good_writes,
                    "existing": existing_textures,
                    "incomplete": incomplete_textures,
                    "error": error_write_textures,
                    "empty": empty_textures,
                }

                progress.update()
                progress.set_postfix({k: v for k, v in postfix.items() if v})

            end(
                args=args,
                good_writes=good_writes,
                incomplete_textures=incomplete_textures,
                existing_textures=existing_textures,
                error_write_textures=error_write_textures,
                empty_textures=empty_textures,
            )

            if args.output_mode == "files" and good_writes == 0:
                print("warning: no textures were written")
                sys.exit(73)
