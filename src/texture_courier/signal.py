import signal
from contextlib import ContextDecorator
import sys
from types import FrameType
from typing import Any, Callable, Self, TypeAlias

Handlers: TypeAlias = Callable[[int, FrameType | None], Any] | int | None


class interrupthandler(ContextDecorator):
    interrupted: bool = False
    original_sigint_handler: Handlers

    def __init__(self) -> None:
        self.original_sigint_handler: Handlers = signal.getsignal(signal.SIGINT)

    def __enter__(self) -> Self:
        signal.signal(signal.SIGINT, self.handler)

        return self

    def __exit__(self, *exc: Any) -> None:
        signal.signal(signal.SIGINT, self.original_sigint_handler)

        if self.interrupted:
            sys.exit(130)

    def handler(self, signalnum: int, frame: FrameType | None) -> None:
        self.interrupted = True
