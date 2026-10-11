import math
import unittest

from market_intelligence.indicators import calculate, ema, wilder
from market_intelligence.models import Interval
from market_intelligence.validation import parse_klines

from tests.fixtures import rows


class IndicatorTests(unittest.TestCase):
    def test_seeds_and_hand_computed_averages(self) -> None:
        self.assertEqual(ema([1, 2, 3, 4], 3), [2, 3])
        self.assertAlmostEqual(wilder([1, 2, 3, 4], 3), 8 / 3)

    def test_flat_market(self) -> None:
        f = calculate(parse_klines(rows(Interval.H1, slope=0)))
        self.assertEqual(f.ema20, 100)
        self.assertEqual(f.sma20, 100)
        self.assertEqual(f.atr14, 2)
        self.assertEqual(f.rsi14, 50)
        self.assertEqual(f.obv, 0)
        self.assertEqual(f.realized_volatility20, 0)
        self.assertEqual(f.efficiency20, 0)
        self.assertEqual(f.volume_ratio20, 1)

    def test_rising_and_falling_rsi_and_obv(self) -> None:
        for slope, expected_rsi, sign in ((0.1, 100, 1), (-0.1, 0, -1)):
            f = calculate(parse_klines(rows(Interval.H1, slope=slope)))
            self.assertEqual(f.rsi14, expected_rsi)
            self.assertEqual(f.obv, sign * 2490)
            self.assertAlmostEqual(f.efficiency20, 1)

    def test_zero_volume_and_zero_range_are_defined(self) -> None:
        data = rows(Interval.H1, slope=0)
        for row in data:
            row[2] = row[3] = row[4]
            row[5] = row[7] = "0"
        f = calculate(parse_klines(data))
        self.assertIsNone(f.volume_ratio20)
        self.assertEqual(f.atr14, 0)
        self.assertEqual(f.ema_gap_atr, 0)

    def test_mixed_rsi_matches_wilder_reference(self) -> None:
        data = rows(Interval.H1)
        prices = [100 + math.sin(i) for i in range(250)]
        for row, price in zip(data, prices):
            row[1], row[2], row[3], row[4] = str(price), str(price + 1), str(price - 1), str(price)
        deltas = [b - a for a, b in zip(prices, prices[1:])]
        gain = sum(max(x, 0) for x in deltas[:14]) / 14
        loss = sum(max(-x, 0) for x in deltas[:14]) / 14
        for d in deltas[14:]:
            gain += (max(d, 0) - gain) / 14
            loss += (max(-d, 0) - loss) / 14
        self.assertAlmostEqual(calculate(parse_klines(data)).rsi14, 100 - 100 / (1 + gain / loss))

    def test_insufficient_history(self) -> None:
        with self.assertRaises(ValueError):
            calculate(parse_klines(rows(Interval.H1, count=99)))
