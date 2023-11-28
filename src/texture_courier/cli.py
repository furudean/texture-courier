import argparse
from io import BytesIO
from pathlib import Path
import os
from PIL import Image, UnidentifiedImageError

from .api import TextureCache


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="texture-courier",
        description="rips texture cache from second life viewers",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("cache_dir", type=Path, help="path to texture cache directory")
    parser.add_argument(
        "--out-dir",
        "-o",
        type=Path,
        help="path to output assets",
        default="./texturecache",
    )

    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="don't write anything to disk",
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
        "-v", action="store_true", help="more detailed output", default=False
    )

    args = parser.parse_args()

    if (
        args.force is True
        or args.dry_run is False
        or (args.out_dir.exists() and any(args.out_dir.iterdir()))
    ):
        print(f"output directory {args.out_dir} already exists")
        exit(1)
    else:
        args.out_dir.mkdir(exist_ok=True)

    good_writes = 0
    bad_writes = 0

    cache = TextureCache(args.cache_dir)

    for entry in cache:
        uuid = entry.entry["uuid"]

        if entry.ok is False:
            continue

        image_bytes = BytesIO(entry.loads())

        try:
            if args.dry_run:
                save_path: Path = Path(os.devnull)
            else:
                save_path = args.out_dir / f"{uuid}.jp2"

            # the cache stores files in a raw codestream format that is hard for
            # most operating systems to read, and isn't intended to be used for
            # storage. loading it with pillow and saving it seems to produce a
            # correct image. it is slow, however.
            with Image.open(image_bytes, formats=["jpeg2000"]) as im:
                im.save(save_path)

            print(save_path.resolve())
            good_writes += 1
        except (UnidentifiedImageError, OSError):
            bad_writes += 1
            continue

    # if args.v:
    print("")
    print(f"wrote {good_writes} cache entries")
    print(f"failed to save {bad_writes} entries") if bad_writes else None

    if not good_writes:
        exit(1)
