import unittest
from dataclasses import replace

from market_intelligence.models import Interval, MarketError
from market_intelligence.validation import parse_klines, validate

from tests.fixtures import CUTOFF, rows


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candles = parse_klines(rows(Interval.H1))

    def check_bad(self, candles: tuple) -> None:
        self.assertFalse(validate(candles, Interval.H1, CUTOFF)[1].valid)

    def test_valid_all_intervals(self) -> None:
        for interval in Interval:
            with self.subTest(interval=interval):
                self.assertTrue(validate(parse_klines(rows(interval)), interval, CUTOFF)[1].valid)

    def test_gaps_duplicates_order(self) -> None:
        self.check_bad(self.candles[:10] + self.candles[11:])
        self.check_bad(self.candles[:10] + self.candles[9:])
        self.check_bad(tuple(reversed(self.candles)))

    def test_invalid_prices_volumes_and_timestamps(self) -> None:
        for change in (
            {"high": 1.0},
            {"low": 0.0},
            {"volume": -1.0},
            {"close": float("nan")},
            {"open": float("inf")},
            {"quote_volume": -1.0},
            {"trades": -1},
            {"open_time_ms": self.candles[-1].open_time_ms + 1},
            {"close_time_ms": self.candles[-1].close_time_ms - 1},
        ):
            with self.subTest(change=change):
                self.check_bad(self.candles[:-1] + (replace(self.candles[-1], **change),))

    def test_stale_and_short(self) -> None:
        self.check_bad(self.candles[:-1])
        self.check_bad(self.candles[-99:])

    def test_open_and_future_candles_excluded(self) -> None:
        step = Interval.H1.milliseconds
        future = replace(
            self.candles[-1], open_time_ms=CUTOFF, close_time_ms=CUTOFF + step - 1, close=999999.0
        )
        closed, report = validate(self.candles + (future,), Interval.H1, CUTOFF)
        self.assertEqual(closed, self.candles)
        self.assertTrue(report.valid)
        self.assertEqual(report.excluded_unclosed, 1)

    def test_inclusive_close_boundary(self) -> None:
        closed, _ = validate(self.candles, Interval.H1, self.candles[-1].close_time_ms)
        self.assertEqual(closed, self.candles[:-1])

    def test_parse_rejects_bad_shape_and_fractional_timestamps(self) -> None:
        for value in ({"code": -1121}, [[1, 2]], [[True] * 12], [[1.5] * 12]):
            with self.subTest(value=value), self.assertRaises(MarketError):
                parse_klines(value)
