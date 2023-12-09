import math


def format_bytes(size: float) -> str:
    power = 2**10
    n = 0
    power_labels = {0: "bytes", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}

    while size > power:
        size /= power
        n += 1

    return f"{math.ceil(size)} {power_labels[n]}"
