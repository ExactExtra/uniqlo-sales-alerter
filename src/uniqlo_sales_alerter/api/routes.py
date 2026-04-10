"""FastAPI REST endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from uniqlo_sales_alerter.models.products import SaleCheckResult, SaleItem

router = APIRouter(prefix="/api/v1")

_NO_RESULT = HTTPException(
    status_code=503, detail="No sale check has been run yet",
)


def _latest_result() -> SaleCheckResult:
    from uniqlo_sales_alerter.main import state

    result = state.sale_checker.last_result
    if result is None:
        raise _NO_RESULT
    return result


@router.get("/sales", response_model=SaleCheckResult)
async def get_sales(
    gender: str | None = Query(
        None, description="Filter by gender (men/women/unisex)",
    ),
    min_discount: float | None = Query(
        None, ge=0, le=100, description="Override minimum discount %",
    ),
) -> SaleCheckResult:
    """Return the latest cached sale-check results, optionally filtered."""
    result = _latest_result()
    deals = result.matching_deals

    if gender is not None:
        g = gender.upper()
        deals = [
            d for d in deals
            if d.gender.upper() in (g, "UNISEX")
        ]
    if min_discount is not None:
        deals = [d for d in deals if d.discount_percentage >= min_discount]

    deal_ids = {d.product_id for d in deals}
    return SaleCheckResult(
        checked_at=result.checked_at,
        total_products_scanned=result.total_products_scanned,
        total_on_sale=result.total_on_sale,
        matching_deals=deals,
        new_deals=[
            d for d in result.new_deals if d.product_id in deal_ids
        ],
    )


@router.post("/sales/check", response_model=SaleCheckResult)
async def trigger_check() -> SaleCheckResult:
    """Trigger an immediate sale check."""
    from uniqlo_sales_alerter.main import run_sale_check, state

    return await run_sale_check(state)


@router.get("/products/{product_id}", response_model=SaleItem)
async def get_product(product_id: str) -> SaleItem:
    """Look up a specific product in the latest results."""
    result = _latest_result()
    for deal in result.matching_deals:
        if deal.product_id == product_id:
            return deal
    raise HTTPException(
        status_code=404,
        detail=f"Product {product_id} not found in current deals",
    )


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """Return the active configuration (secrets are redacted)."""
    from uniqlo_sales_alerter.main import state

    data = state.config.model_dump()

    tg = data.get("notifications", {}).get("channels", {}).get("telegram", {})
    if tg.get("bot_token"):
        tg["bot_token"] = "***"
    email = data.get("notifications", {}).get("channels", {}).get("email", {})
    if email.get("smtp_password"):
        email["smtp_password"] = "***"

    return data
