import argparse
from pathlib import Path

from .cache import (
    loads_bytes,
    decode_header,
    decode_entries,
    read_texture_cache,
    read_texture_body,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="texture_courier",
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
        "-v", action="store_true", help="more detailed output", default=False
    )

    args = parser.parse_args()

    texture_entries = loads_bytes(args.cache_dir / "texture.entries")
    texture_cache = loads_bytes(args.cache_dir / "texture.cache")

    header = decode_header(texture_entries)
    # print(header)

    entries = decode_entries(texture_entries, entry_count=header["entry_count"])

    good_reads = 0
    bad_reads = 0

    if args.out_dir.exists():
        print(f"output directory {args.out_dir} already exists")
        exit(1)

    args.out_dir.mkdir(exist_ok=True)

    for i, entry in enumerate(entries):
        uuid = entry["uuid"]
        save_path: Path = args.out_dir / f"{uuid}.j2c"

        head = read_texture_cache(texture_cache, i)
        body = read_texture_body(uuid, cache_dir=args.cache_dir)

        if head is None or body is None:
            bad_reads += 1
            continue

        j2c_bytes = head + body

        with open(save_path, "wb") as f:
            f.write(j2c_bytes)

        print(save_path.resolve())

        good_reads += 1

    if args.v:
        print("")
        print(f"wrote {good_reads} cache entries")
        print(f"failed to read {bad_reads} entries") if bad_reads else None


if __name__ == "__main__":
    main()
