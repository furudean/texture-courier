import os
from collections.abc import Callable
from pathlib import Path

import pytest

# workload name, peak bytes, bytes still held once it returns
memory_results: list[tuple[str, int, int]] = []


def pytest_configure() -> None:
    if not os.environ.get("CACHE_DIR"):
        raise pytest.UsageError("set CACHE_DIR to the texture cache to benchmark")


@pytest.fixture(scope="session")
def cache_dir() -> Path:
    return Path(os.environ["CACHE_DIR"])


@pytest.fixture
def record_memory() -> Callable[[str, int, int], None]:
    return lambda name, peak, held: memory_results.append((name, peak, held))


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    if not memory_results:
        return

    terminalreporter.section("memory")

    width = max(len(name) for name, _, _ in memory_results)

    terminalreporter.write_line(f"{'workload':<{width}}  {'peak':>10}  {'held':>10}")

    for name, peak, held in memory_results:
        terminalreporter.write_line(f"{name:<{width}}  {peak / 2**20:>7.1f} MB  {held / 2**20:>7.1f} MB")
