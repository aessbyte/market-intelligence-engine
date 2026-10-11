import io
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from market_intelligence.binance import BinanceClient, PublicHTTP, normalize_symbol
from market_intelligence.models import Interval, MarketError

from tests.fixtures import CUTOFF, FakeBinance


class BinanceTests(unittest.TestCase):
    def test_symbol_normalization(self) -> None:
        self.assertEqual(normalize_symbol(" btcusdt "), "BTCUSDT")
        for symbol in ("BTC/USDT", "../orders", "", "BTCUSDT&secret=1"):
            with self.assertRaises(MarketError):
                normalize_symbol(symbol)

    def test_public_endpoints_no_keys(self) -> None:
        fake = FakeBinance()
        result = BinanceClient(fake).snapshot("ETHUSDT", source="simulated")
        self.assertEqual(result["symbol"], "ETHUSDT")
        self.assertEqual(len(fake.calls), 5)
        self.assertEqual(
            {path for path, _ in fake.calls},
            {"/api/v3/time", "/api/v3/exchangeInfo", "/api/v3/klines"},
        )
        self.assertTrue(all("signature" not in p and "apiKey" not in p for _, p in fake.calls))

    def test_pagination_and_closed_end_time(self) -> None:
        fake = FakeBinance()
        data = BinanceClient(fake).klines("BTCUSDT", Interval.H1, CUTOFF + 1000, 1250)
        self.assertEqual(len(data), 1250)
        self.assertEqual([p["limit"] for _, p in fake.calls], [1000, 250])
        self.assertTrue(all(p["endTime"] == CUTOFF - 1 for _, p in fake.calls))
        self.assertEqual(len({r[0] for r in data}), 1250)

    def test_invalid_limits_and_future_cutoff(self) -> None:
        client = BinanceClient(FakeBinance())
        for count in (99, 5001):
            with self.assertRaises(MarketError):
                client.snapshot("BTCUSDT", bars=count)
        with self.assertRaises(MarketError):
            client.snapshot("BTCUSDT", as_of_ms=CUTOFF + 1)

    def test_unavailable_symbol_and_bad_time(self) -> None:
        fake = FakeBinance()
        with patch.object(fake, "get", return_value={"serverTime": True}):
            with self.assertRaises(MarketError):
                BinanceClient(fake).server_time()
        for info in ({"symbols": []}, {"symbols": [{"symbol": "BTCUSDT", "status": "HALT"}]}):
            with patch.object(fake, "get", return_value=info), self.assertRaises(MarketError):
                BinanceClient(fake).symbol_info("BTCUSDT")

    def test_http_success_request_has_no_private_headers(self) -> None:
        with patch(
            "market_intelligence.binance.urlopen", return_value=io.BytesIO(b'{"serverTime": 123}')
        ) as mock:
            self.assertEqual(PublicHTTP().get("/api/v3/time", {}), {"serverTime": 123})
            request = mock.call_args.args[0]
            self.assertNotIn("X-mbx-apikey", request.headers)
            self.assertEqual(request.get_method(), "GET")

    def test_retries_rate_limit_and_server_errors(self) -> None:
        for status in (429, 500, 503):
            delay = []
            error = HTTPError("url", status, "error", {"Retry-After": "1000"}, None)
            with patch(
                "market_intelligence.binance.urlopen", side_effect=[error, io.BytesIO(b"[]")]
            ) as mock:
                self.assertEqual(PublicHTTP(sleep=delay.append).get("/api/v3/klines", {}), [])
                self.assertEqual(mock.call_count, 2)
                self.assertEqual(delay, [30])

    def test_no_retry_for_client_or_geographic_error(self) -> None:
        for status in (400, 401, 403, 418, 451):
            with patch(
                "market_intelligence.binance.urlopen",
                side_effect=HTTPError("url", status, "error", {}, None),
            ) as mock:
                with self.assertRaises(MarketError):
                    PublicHTTP(sleep=lambda _: None).get("/api/v3/time", {})
                self.assertEqual(mock.call_count, 1)

    def test_network_retry_exhaustion_and_malformed_json(self) -> None:
        with patch("market_intelligence.binance.urlopen", side_effect=URLError("offline")) as mock:
            with self.assertRaises(MarketError):
                PublicHTTP(sleep=lambda _: None).get("/api/v3/time", {})
            self.assertEqual(mock.call_count, 3)
        with patch("market_intelligence.binance.urlopen", return_value=io.BytesIO(b"<html>")):
            with self.assertRaises(MarketError):
                PublicHTTP().get("/api/v3/time", {})

    def test_disallows_order_and_private_endpoints(self) -> None:
        with self.assertRaises(MarketError):
            PublicHTTP().get("/api/v3/order", {})

    def test_pagination_rejects_nonprogressing_response(self) -> None:
        fake = FakeBinance()
        with patch.object(fake, "get", return_value=[[0] * 12]), self.assertRaises(MarketError):
            BinanceClient(fake).klines("BTCUSDT", Interval.H1, CUTOFF, 250)
