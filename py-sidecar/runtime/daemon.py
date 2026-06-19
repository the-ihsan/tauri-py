from __future__ import annotations

from collections.abc import Callable

from builder_app import BuilderApp
from facade import Facade
from modules import get_modules
from registry import Registry
from transport import Transport
from error_log import error_log


def main() -> None:
    registry = Registry()
    transport = Transport(registry)
    facade = Facade(transport.enqueue)

    builder = BuilderApp(facade, registry)
    for module in get_modules():
        module(builder)

    transport.start(facade)


if __name__ == "__main__":
    main()
