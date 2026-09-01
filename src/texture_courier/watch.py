"""Live updates for a texture cache a viewer is still writing to"""

import logging
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Self

from .error import TextureCacheError

if TYPE_CHECKING:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers.api import BaseObserver, ObservedWatch

    from .api import Texture, TextureCache

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 0.2
DEBOUNCE_LIMIT_SECONDS = 2.0

_observer_lock = threading.Lock()
_observer: "BaseObserver | None" = None
_scheduled: dict[str, tuple["ObservedWatch", int]] = {}


def schedule(event_handler: "FileSystemEventHandler", path: str) -> None:
    global _observer

    with _observer_lock:
        if _observer is None:
            from watchdog.observers import Observer

            _observer = Observer()
            _observer.start()

        existing = _scheduled.get(path)

        if existing is None:
            watch, count = _observer.schedule(event_handler, path), 0
        else:
            watch, count = existing
            _observer.add_handler_for_watch(event_handler, watch)

        _scheduled[path] = (watch, count + 1)


def unschedule(event_handler: "FileSystemEventHandler", path: str) -> None:
    global _observer

    with _observer_lock:
        existing = _scheduled.get(path)

        if existing is None or _observer is None:
            return

        watch, count = existing
        _observer.remove_handler_for_watch(event_handler, watch)

        if count > 1:
            _scheduled[path] = (watch, count - 1)
            return

        _observer.unschedule(watch)
        del _scheduled[path]

        if not _scheduled:
            _observer.stop()

            # a handler that stops its own watch is calling from the thread
            # that would be joined here
            with suppress(RuntimeError):
                _observer.join()

            _observer = None


def watch_alive(path: str) -> bool:
    with _observer_lock:
        existing = _scheduled.get(path)

        if _observer is None or existing is None or not _observer.is_alive():
            return False

        watch = existing[0]

        return any(emitter.watch == watch and emitter.is_alive() for emitter in _observer.emitters)


class Watch:
    """A running watch over a cache directory, as handed back by TextureCache.watch

    Doubles as a context manager, which stops the watch on the way out.
    """

    cache: "TextureCache"
    path: str

    def __init__(
        self,
        cache: "TextureCache",
        handler: Callable[[list["Texture"]], Any],
        *,
        on_error: Callable[[Exception], Any] | None = None,
        debounce: float = DEBOUNCE_SECONDS,
    ):
        try:
            from watchdog.events import PatternMatchingEventHandler
        except ImportError as e:
            raise ImportError(
                'watching a cache needs watchdog extra. install with "pip install texture-courier[watcher]"'
            ) from e

        self.cache = cache
        self.path = str(cache.cache_dir.resolve())

        self.__handler = handler
        self.__on_error = on_error
        self.__debounce = debounce
        self.__lock = threading.Lock()
        self.__timer: threading.Timer | None = None
        self.__deadline: float | None = None
        self.__stopped = threading.Event()

        event_handler = PatternMatchingEventHandler(patterns=["texture.entries"], ignore_directories=True)

        # every kind of event rather than modifications alone. a viewer that
        # swaps the file in by rename reports a move on linux and nothing more,
        # and one that empties the cache reports a delete and a create
        event_handler.on_any_event = self.__on_event  # type: ignore[method-assign]

        self.__event_handler = event_handler

        schedule(event_handler, self.path)

        # a write that landed between the cache's last read and the watch going
        # up would otherwise sit there unreported
        self.__arm()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def __on_event(self, event: "FileSystemEvent") -> None:
        self.__arm()

    def __arm(self) -> None:
        with self.__lock:
            if self.__stopped.is_set():
                return

            now = time.monotonic()

            if self.__deadline is None:
                self.__deadline = now + DEBOUNCE_LIMIT_SECONDS

            if self.__timer is not None:
                self.__timer.cancel()

            self.__timer = threading.Timer(min(self.__debounce, max(self.__deadline - now, 0)), self.__read)
            self.__timer.daemon = True
            self.__timer.start()

    def __read(self) -> None:
        with self.__lock:
            self.__deadline = None

        try:
            changed_textures = list(self.cache.refresh())
        except (TextureCacheError, OSError) as error:
            # a viewer part way through rewriting texture.entries leaves it
            # briefly inconsistent. the cache keeps hold of its last good copy,
            # so the event that follows the write reads it properly
            self.__report(error)

            return

        if not changed_textures:
            return

        try:
            self.__handler(changed_textures)
        except Exception as error:  # noqa: BLE001
            # a handler belongs to the caller and gets to be wrong without
            # taking the watch down with it
            self.__report(error)

    def __report(self, error: Exception) -> None:
        if self.__on_error is None:
            logger.debug("watch on %s could not read a change", self.path, exc_info=error)

            return

        self.__on_error(error)

    def is_alive(self) -> bool:
        return not self.__stopped.is_set() and watch_alive(self.path)

    def stop(self) -> None:
        with self.__lock:
            if self.__stopped.is_set():
                return

            self.__stopped.set()
            timer, self.__timer = self.__timer, None

        if timer is not None:
            timer.cancel()

        unschedule(self.__event_handler, self.path)

    def join(self, timeout: float | None = None) -> None:
        """Block until the watch is stopped, or until timeout seconds have passed"""
        self.__stopped.wait(timeout)
