import argparse
from io import BytesIO
from pathlib import Path
from PIL import Image, UnidentifiedImageError


from .api import TextureCache, TextureError


def is_dir_dirty(path: Path) -> bool:
    try:
        return any(path.iterdir())
    except FileNotFoundError:
        return False


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
        "--force",
        "-f",
        action="store_true",
        help="overwrite output files",
        default=False,
    )

    parser.add_argument(
        "--raw",
        action="store_true",
        help="skip decoding and just save the raw codestream",
        default=False,
    )

    # parser.add_argument(
    #     "-v", action="store_true", help="more detailed output", default=False
    # )

    args = parser.parse_args()

    existing_textures = 0
    good_writes = 0

    cache = TextureCache(args.cache_dir)

    print(cache.header)
    print("")

    args.out_dir.mkdir(exist_ok=True)

    for texture in cache:
        uuid = texture.entry["uuid"]

        if texture.error == TextureError.EMPTY:
            continue

        image_bytes = texture.loads()

        if args.raw is False:
            save_path: Path = args.out_dir / f"{uuid}.jp2"

            if save_path.exists() and not args.force:
                existing_textures += 1
                continue

            try:
                # the cache stores files in a raw codestream format that is hard for
                # most operating systems to read, and isn't intended to be used for
                # storage. loading it with pillow and saving it seems to produce a
                # correct image. it is slow, however.
                with Image.open(BytesIO(image_bytes), formats=["jpeg2000"]) as im:
                    im.save(save_path)
            except OSError:
                texture.error = TextureError.WRITE_ERROR
                continue
        else:
            save_path = args.out_dir / f"{uuid}.j2c"

            save_path.write_bytes(image_bytes)

        print(save_path.resolve())
        good_writes += 1

    error_write_textures = [
        texture for texture in cache if texture.error == TextureError.WRITE_ERROR
    ]
    empty_textures = [
        texture for texture in cache if texture.error == TextureError.EMPTY
    ]

    print("")
    print(f"wrote {good_writes} textures")
    print(
        f"failed to write {len(error_write_textures)} textures"
    ) if error_write_textures else None
    print(
        f"skipped {existing_textures} existing textures"
    ) if existing_textures else None
    print(f"skipped {len(empty_textures)} empty textures") if empty_textures else None

    # print([texture.entry for texture in error_write_textures])

    if not good_writes:
        print("error: nothing was extracted successfully")
        exit(1)
