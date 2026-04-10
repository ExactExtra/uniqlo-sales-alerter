"""Console notification channel — prints deals to stdout for preview/dry-run."""

from __future__ import annotations

import sys

from uniqlo_sales_alerter.models.products import SaleItem

# ANSI colour codes (disabled if stdout is not a terminal)
_USE_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def _format_deal(deal: SaleItem, index: int) -> str:
    watched = _c("33", " [WATCHED]") if deal.is_watched else ""
    header = _c("1", f"  {index}. {deal.name}") + watched
    price_line = (
        f"     {_c('9', f'{deal.currency_symbol}{deal.original_price:.2f}')}"
        f" -> {_c('32;1', f'{deal.currency_symbol}{deal.sale_price:.2f}')}"
        f"  {_c('32', f'(-{deal.discount_percentage:.0f}%)')}"
    )
    lines = [header, price_line]
    for size, url in zip(deal.available_sizes, deal.product_urls):
        lines.append(f"     {_c('36', size):>8s}  {url}")
    return "\n".join(lines)


class ConsoleNotifier:
    """Prints deal summaries to stdout. Used in preview / dry-run mode."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    async def send(self, deals: list[SaleItem]) -> None:
        if not deals:
            print("\n  No deals to display.\n")
            return

        print(_c("1;36", f"\n{'=' * 60}"))
        print(_c("1;36", f"  Uniqlo Sale Alert — {len(deals)} deal(s)"))
        print(_c("1;36", f"{'=' * 60}"))

        for i, deal in enumerate(deals, 1):
            print()
            print(_format_deal(deal, i))

        print()
        print(_c("2", "  https://github.com/kequach/uniqlo-sales-alerter"))
        print()
