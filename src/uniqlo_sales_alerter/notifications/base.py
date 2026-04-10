"""Protocol that all notification channels must satisfy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from uniqlo_sales_alerter.models.products import SaleItem


@runtime_checkable
class Notifier(Protocol):
    """Structural interface for notification channels.

    Any class with matching ``send`` and ``is_enabled`` signatures is
    automatically considered a ``Notifier`` — no inheritance required.
    """

    def is_enabled(self) -> bool: ...

    async def send(self, deals: list[SaleItem]) -> None: ...
