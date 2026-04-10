"""Tests for the Uniqlo API client with mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from uniqlo_sales_alerter.clients.uniqlo import (
    UniqloClient,
    _backoff_seconds,
    _retry_after,
)
from uniqlo_sales_alerter.config import AppConfig

from .conftest import make_api_response, make_raw_product


@pytest.fixture()
def config() -> AppConfig:
    return AppConfig.model_validate({"uniqlo": {"country": "de/de"}})


@pytest.fixture()
async def client(config: AppConfig):
    c = UniqloClient(config)
    yield c
    await c.aclose()


class TestFetchSaleProducts:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_sale_products(self, client: UniqloClient, config: AppConfig):
        products = [
            make_raw_product(product_id=f"E{i:06d}-000", promo_price=10.0)
            for i in range(3)
        ]
        response = make_api_response(products, total=3)
        respx.get(config.base_url).mock(
            return_value=httpx.Response(200, json=response)
        )

        result = await client.fetch_sale_products()
        assert len(result) == 3
        assert result[0].product_id == "E000000-000"

    @pytest.mark.asyncio
    @respx.mock
    async def test_sale_products_sends_flagcodes_param(
        self, client: UniqloClient, config: AppConfig
    ):
        response = make_api_response([], total=0)
        route = respx.get(config.base_url).mock(
            return_value=httpx.Response(200, json=response)
        )

        await client.fetch_sale_products()

        assert route.called
        request = route.calls[0].request
        assert "flagCodes=discount" in str(request.url)


class TestFetchAllProducts:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_single_page(
        self, client: UniqloClient, config: AppConfig
    ):
        products = [
            make_raw_product(product_id=f"E{i:06d}-000") for i in range(3)
        ]
        response = make_api_response(products, total=3)
        respx.get(config.base_url).mock(
            return_value=httpx.Response(200, json=response)
        )

        result = await client.fetch_all_products()
        assert len(result) == 3
        assert result[0].product_id == "E000000-000"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_with_pagination(
        self, client: UniqloClient, config: AppConfig
    ):
        page1 = [
            make_raw_product(product_id=f"E{i:06d}-000") for i in range(100)
        ]
        page2 = [
            make_raw_product(product_id=f"E{i:06d}-000")
            for i in range(100, 130)
        ]

        page1_resp = make_api_response(page1, total=130)
        page1_resp["result"]["pagination"]["count"] = 100
        page2_resp = make_api_response(page2, total=130)
        page2_resp["result"]["pagination"]["offset"] = 100
        page2_resp["result"]["pagination"]["count"] = 30

        route = respx.get(config.base_url)
        route.side_effect = [
            httpx.Response(200, json=page1_resp),
            httpx.Response(200, json=page2_resp),
        ]

        result = await client.fetch_all_products()
        assert len(result) == 130


class TestErrorHandling:
    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_api_error_status(
        self, client: UniqloClient, config: AppConfig
    ):
        error_resp = {
            "status": "nok",
            "error": {"code": 0, "details": [{"message": "error"}]},
        }
        respx.get(config.base_url).mock(
            return_value=httpx.Response(200, json=error_resp)
        )

        result = await client.fetch_sale_products()
        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_http_500(
        self, client: UniqloClient, config: AppConfig
    ):
        respx.get(config.base_url).mock(
            return_value=httpx.Response(500)
        )

        result = await client.fetch_sale_products()
        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_sends_correct_headers(
        self, client: UniqloClient, config: AppConfig
    ):
        response = make_api_response([], total=0)
        route = respx.get(config.base_url).mock(
            return_value=httpx.Response(200, json=response)
        )

        await client.fetch_all_products()

        assert route.called
        request = route.calls[0].request
        assert request.headers["x-fr-clientid"] == "uq.de.web-spa"
        assert request.headers["accept"] == "application/json"


class TestFetchProductL2s:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_l2_variants(
        self, client: UniqloClient, config: AppConfig,
    ):
        l2_data = [
            {"l2Id": "abc", "color": {"displayCode": "01"}, "size": {"name": "M"}},
        ]
        url = f"{config.base_url}/E123-000/price-groups/00"
        respx.get(url).mock(
            return_value=httpx.Response(200, json={"result": {"l2s": l2_data}}),
        )

        result = await client.fetch_product_l2s("E123-000", "00")
        assert len(result) == 1
        assert result[0]["l2Id"] == "abc"

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_empty_on_http_error(
        self, client: UniqloClient, config: AppConfig,
    ):
        url = f"{config.base_url}/E123-000/price-groups/00"
        respx.get(url).mock(return_value=httpx.Response(500))

        result = await client.fetch_product_l2s("E123-000", "00")
        assert result == []


class TestFetchVariantStock:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_stock_map(
        self, client: UniqloClient, config: AppConfig,
    ):
        stock_data = {"abc": {"statusCode": "IN_STOCK", "quantity": 5}}
        url = f"{config.base_url}/E123-000/price-groups/00/stock"
        respx.get(url).mock(
            return_value=httpx.Response(200, json={"result": stock_data}),
        )

        result = await client.fetch_variant_stock("E123-000", "00")
        assert result["abc"]["statusCode"] == "IN_STOCK"

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_empty_on_http_error(
        self, client: UniqloClient, config: AppConfig,
    ):
        url = f"{config.base_url}/E123-000/price-groups/00/stock"
        respx.get(url).mock(return_value=httpx.Response(500))

        result = await client.fetch_variant_stock("E123-000", "00")
        assert result == {}


class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_aclose_idempotent(self, config: AppConfig):
        c = UniqloClient(config)
        await c.aclose()
        await c.aclose()  # should not raise

    @pytest.mark.asyncio
    @respx.mock
    async def test_shared_client_reused_across_calls(
        self, client: UniqloClient, config: AppConfig,
    ):
        """Ensure the same httpx.AsyncClient is reused, not recreated."""
        url = f"{config.base_url}/E1-000/price-groups/00"
        respx.get(url).mock(
            return_value=httpx.Response(200, json={"result": {"l2s": []}}),
        )

        await client.fetch_product_l2s("E1-000", "00")
        first_client = client._client

        await client.fetch_product_l2s("E1-000", "00")
        assert client._client is first_client


class TestRateLimitHandling:
    """Tests for 429 / retry / backoff behaviour in _request."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_retries_then_succeeds(
        self, client: UniqloClient, config: AppConfig,
    ):
        """A single 429 followed by a 200 should succeed."""
        l2_data = [{"l2Id": "x"}]
        url = f"{config.base_url}/E1-000/price-groups/00"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json={"result": {"l2s": l2_data}}),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_product_l2s("E1-000", "00")

        assert len(result) == 1
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_exhausts_retries_returns_empty(
        self, client: UniqloClient, config: AppConfig,
    ):
        """Three consecutive 429s should exhaust retries; L2 returns []."""
        url = f"{config.base_url}/E1-000/price-groups/00"
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"retry-after": "0"}),
        )

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_product_l2s("E1-000", "00")

        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_on_stock_retries_then_succeeds(
        self, client: UniqloClient, config: AppConfig,
    ):
        stock_data = {"abc": {"statusCode": "IN_STOCK", "quantity": 3}}
        url = f"{config.base_url}/E1-000/price-groups/00/stock"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json={"result": stock_data}),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_variant_stock("E1-000", "00")

        assert result["abc"]["statusCode"] == "IN_STOCK"
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_on_page_fetch_retries(
        self, client: UniqloClient, config: AppConfig,
    ):
        """Pagination should also retry on 429."""
        products = [make_raw_product(product_id="E000001-000", promo_price=10.0)]
        ok_resp = make_api_response(products, total=1)

        route = respx.get(config.base_url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json=ok_resp),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_sale_products()

        assert len(result) == 1
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_503_retries_then_succeeds(
        self, client: UniqloClient, config: AppConfig,
    ):
        """503 (service unavailable) should also be retried."""
        l2_data = [{"l2Id": "y"}]
        url = f"{config.base_url}/E1-000/price-groups/00"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json={"result": {"l2s": l2_data}}),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_product_l2s("E1-000", "00")

        assert len(result) == 1
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_retry_after_header_respected(
        self, client: UniqloClient, config: AppConfig,
    ):
        """When the server sends Retry-After: 7, we should sleep ~7s."""
        l2_data = [{"l2Id": "z"}]
        url = f"{config.base_url}/E1-000/price-groups/00"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "7"}),
            httpx.Response(200, json={"result": {"l2s": l2_data}}),
        ]

        with patch(
            "uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep",
        ) as mock_sleep:
            await client.fetch_product_l2s("E1-000", "00")

        mock_sleep.assert_awaited_once_with(7.0)

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_prints_to_console(
        self, client: UniqloClient, config: AppConfig, capsys,
    ):
        """A 429 should print a visible message to stdout."""
        url = f"{config.base_url}/E1-000/price-groups/00"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json={"result": {"l2s": []}}),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            await client.fetch_product_l2s("E1-000", "00")

        output = capsys.readouterr().out
        assert "[Rate limit]" in output
        assert "429" in output

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_exhausted_prints_gave_up(
        self, client: UniqloClient, config: AppConfig, capsys,
    ):
        """When all retries fail on 429, a 'gave up' message is printed."""
        url = f"{config.base_url}/E1-000/price-groups/00"
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"retry-after": "0"}),
        )

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            await client.fetch_product_l2s("E1-000", "00")

        output = capsys.readouterr().out
        assert "Gave up" in output


class TestBackoffHelpers:
    def test_backoff_without_jitter(self):
        assert _backoff_seconds(1, jitter=False) == 2.0
        assert _backoff_seconds(2, jitter=False) == 4.0
        assert _backoff_seconds(3, jitter=False) == 8.0

    def test_backoff_capped_at_max(self):
        assert _backoff_seconds(10, jitter=False) == 60.0

    def test_backoff_with_jitter_in_range(self):
        for _ in range(50):
            val = _backoff_seconds(2, jitter=True)
            assert 2.0 <= val <= 6.0

    def test_retry_after_numeric(self):
        resp = httpx.Response(429, headers={"retry-after": "10"})
        assert _retry_after(resp) == 10.0

    def test_retry_after_capped(self):
        resp = httpx.Response(429, headers={"retry-after": "999"})
        assert _retry_after(resp) == 60.0

    def test_retry_after_missing(self):
        resp = httpx.Response(429)
        assert _retry_after(resp) is None

    def test_retry_after_non_numeric(self):
        resp = httpx.Response(429, headers={"retry-after": "not-a-number"})
        assert _retry_after(resp) is None
