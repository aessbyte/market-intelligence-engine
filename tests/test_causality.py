import unittest
import math

from market_intelligence.structure import analyze_structure
from market_intelligence.wyckoff import analyze_wyckoff

from tests.task02_fixtures import (
    INTERVAL,
    SHORT_RANGE,
    SOS_LPS,
    SPRING,
    STEP,
    STRUCTURE_PRICES,
    UPTHRUST,
    prices,
    range_candles,
)


class CausalityTests(unittest.TestCase):
    def test_every_prefix_structure_and_wyckoff_journal(self) -> None:
        for data in (
            prices(STRUCTURE_PRICES),
            range_candles(SPRING),
            range_candles(UPTHRUST),
            range_candles(SOS_LPS),
        ):
            end = len(data) * STEP
            full_structure = analyze_structure(data, INTERVAL, end)
            full_wyckoff = analyze_wyckoff(data, INTERVAL, end, full_structure, SHORT_RANGE)
            for n in range(1, len(data) + 1):
                with self.subTest(n=n, size=len(data)):
                    cutoff = n * STEP
                    prefix = data[:n]
                    structure = analyze_structure(prefix, INTERVAL, cutoff)
                    wyckoff = analyze_wyckoff(prefix, INTERVAL, cutoff, structure, SHORT_RANGE)
                    for full, part in ((full_structure, structure), (full_wyckoff, wyckoff)):
                        visible = [
                            e for e in full["event_journal"] if e["available_at_ms"] <= cutoff
                        ]
                        self.assertEqual(visible, part["event_journal"])
                        for event in part["events"]:
                            self.assertLessEqual(event["available_at_ms"], cutoff)
                            if event["state"] == "confirmed":
                                self.assertLessEqual(event["confirmed_at_ms"], cutoff)

    def test_full_input_at_prefix_cutoff_equals_prefix_result(self) -> None:
        data = range_candles(SOS_LPS)
        for n in range(1, len(data) + 1):
            cutoff = n * STEP
            a = analyze_structure(data, INTERVAL, cutoff)
            b = analyze_structure(data[:n], INTERVAL, cutoff)
            self.assertEqual(a, b)
            self.assertEqual(
                analyze_wyckoff(data, INTERVAL, cutoff, a, SHORT_RANGE),
                analyze_wyckoff(data[:n], INTERVAL, cutoff, b, SHORT_RANGE),
            )

    def test_no_confirmation_at_candle_close_inclusive_boundary(self) -> None:
        data = prices([100, 105, 110, 105, 100])
        result = analyze_structure(data, INTERVAL, data[-1].close_time_ms)
        event = next(e for e in result["events"] if e["kind"] == "swing_high")
        self.assertEqual(event["state"], "candidate")

    def test_long_mixed_history_all_prefixes_and_repeated_ranges(self) -> None:
        # Fixed analytic synthetic signal, never observed prices.
        values = [100 + 5 * math.sin(i * 0.7) + 2 * math.sin(i * 0.13) for i in range(120)]
        data = prices(values)
        full = analyze_structure(data, INTERVAL, len(data) * STEP)
        full_w = analyze_wyckoff(data, INTERVAL, len(data) * STEP, full, SHORT_RANGE)
        for n in range(1, len(data) + 1):
            cutoff = n * STEP
            partial = analyze_structure(data[:n], INTERVAL, cutoff)
            partial_w = analyze_wyckoff(data[:n], INTERVAL, cutoff, partial, SHORT_RANGE)
            self.assertEqual(
                partial["event_journal"],
                [e for e in full["event_journal"] if e["available_at_ms"] <= cutoff],
            )
            self.assertEqual(
                partial_w["event_journal"],
                [e for e in full_w["event_journal"] if e["available_at_ms"] <= cutoff],
            )

    def test_deterministic_same_config(self) -> None:
        data = range_candles(SOS_LPS)
        cutoff = len(data) * STEP
        a = analyze_structure(data, INTERVAL, cutoff)
        self.assertEqual(a, analyze_structure(data, INTERVAL, cutoff))
        self.assertEqual(
            analyze_wyckoff(data, INTERVAL, cutoff, a, SHORT_RANGE),
            analyze_wyckoff(data, INTERVAL, cutoff, a, SHORT_RANGE),
        )
