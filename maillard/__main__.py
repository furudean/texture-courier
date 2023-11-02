from io import BytesIO
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from tqdm import tqdm

from cache import (
    loads_bytes,
    decode_header,
    decode_entries,
    read_texture_cache,
    read_texture_body,
)


if __name__ == "__main__":
    out_dir = Path("./out")
    cache_dir = Path.home() / "./Library/Caches/Firestorm_x64/texturecache"

    print(f"using cache file {cache_dir}")

    texture_entries = loads_bytes(cache_dir / "texture.entries")
    texture_cache = loads_bytes(cache_dir / "texture.cache")

    header = decode_header(texture_entries)
    # print(header)

    entries = decode_entries(texture_entries, entry_count=header["entry_count"])

    good_reads = 0
    bad_reads = 0
    skipped_reads = 0

    out_dir.mkdir(exist_ok=True)

    for i, entry in tqdm(enumerate(entries), total=header["entry_count"]):
        uuid = entry["uuid"]
        save_path = out_dir / f"{uuid}.png"

        if save_path.exists():
            skipped_reads += 1
            continue

        head = read_texture_cache(texture_cache, i)
        body = read_texture_body(uuid, cache_dir=cache_dir)

        if head is None:
            bad_reads += 1
            continue

        if body is None:
            j2c_bytes = head
        else:
            j2c_bytes = head + body

        try:
            im = Image.open(BytesIO(j2c_bytes), formats=["jpeg2000"])
            im.save(save_path)

            good_reads += 1
        except (UnidentifiedImageError, OSError):
            bad_reads += 1

    print(f"wrote {good_reads} cache entries")
    print(f"skipped {skipped_reads} duplicates") if skipped_reads else None
    print(f"failed to read {bad_reads} entries") if bad_reads else None
