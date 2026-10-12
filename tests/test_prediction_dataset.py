import copy
import unittest

from market_intelligence.binance import BinanceClient
from market_intelligence.models import Interval, MarketError
from market_intelligence.prediction.dataset import (
    collect_dataset,
    create_dataset,
    dataset_digest,
    validate_dataset,
)
from market_intelligence.validation import parse_klines
from tests.fixtures import CUTOFF, FakeBinance, rows


class DatasetTests(unittest.TestCase):
    def dataset(self):
        return create_dataset(
            rows(Interval.D1),
            "BTCUSDT",
            CUTOFF,
            CUTOFF,
            250,
            "synthetic-fixture",
            {"symbol": "BTCUSDT", "status": "TRADING", "isSpotTradingAllowed": True},
            "simulated",
        )

    def test_reproducible_origin_metadata(self):
        value = self.dataset()
        candles, metadata = validate_dataset(value)
        self.assertEqual(len(candles), 250)
        self.assertEqual(metadata["market"], "spot")
        self.assertTrue(metadata["simulated"])
        self.assertEqual(value, self.dataset())

    def test_changed_candle_or_metadata_rejected(self):
        value = self.dataset()
        value["klines"][0][4] = "777"
        with self.assertRaisesRegex(MarketError, "checksum"):
            validate_dataset(value)
        value = self.dataset()
        value["first_observed_open_ms"] += 1000
        value["dataset_sha256"] = dataset_digest(value)
        with self.assertRaisesRegex(MarketError, "metadata"):
            validate_dataset(value)

    def test_missing_data_not_filled(self):
        value = self.dataset()
        value = create_dataset(
            value["klines"][:10] + value["klines"][11:],
            "BTCUSDT",
            CUTOFF,
            CUTOFF,
            250,
            "fixture",
            value["symbol_info"],
            "simulated",
        )
        self.assertFalse(value["quality"]["valid"])
        with self.assertRaisesRegex(MarketError, "integrity"):
            validate_dataset(value)

    def test_listing_short_history_explicit_not_assumed_date(self):
        value = self.dataset()
        value = create_dataset(
            value["klines"][-100:],
            "BTCUSDT",
            CUTOFF,
            CUTOFF,
            5000,
            "fixture",
            value["symbol_info"],
            "simulated",
        )
        self.assertTrue(value["short_history"])
        self.assertTrue(value["listing_boundary_unknown"])
        self.assertEqual(len(validate_dataset(value)[0]), 100)

    def test_collection_real_no_simulated_fallback(self):
        value = collect_dataset(BinanceClient(FakeBinance()), "BTCUSDT", 250)
        self.assertEqual(value["source"], "binance_public")
        self.assertFalse(value["simulated"])

    def test_boolean_ohlcv_rejected(self):
        for col in (1, 2, 3, 4, 5, 7):
            data = copy.deepcopy(rows(Interval.D1))
            data[0][col] = True
            with self.assertRaisesRegex(MarketError, "boolean"):
                parse_klines(data)
