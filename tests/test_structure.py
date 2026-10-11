import unittest

from market_intelligence.models import MarketError
from market_intelligence.structure import StructureConfig, analyze_structure

from tests.task02_fixtures import INTERVAL, STEP, STRUCTURE_PRICES, prices


class StructureTests(unittest.TestCase):
    def run_engine(self, values: list[float], config: StructureConfig = StructureConfig()) -> dict:
        candles = prices(values)
        return analyze_structure(candles, INTERVAL, len(candles) * STEP, config)

    def test_pivot_delay_and_no_retrospective_confirmation(self) -> None:
        prefix = self.run_engine([100, 105, 110])
        pivot = next(e for e in prefix["events"] if e["kind"] == "swing_high")
        self.assertEqual(pivot["state"], "candidate")
        result = self.run_engine([100, 105, 110, 105, 100])
        pivot = next(
            e
            for e in result["events"]
            if e["event_time_ms"] == 2 * STEP and e["kind"] == "swing_high"
        )
        self.assertEqual(pivot["state"], "confirmed")
        self.assertEqual(pivot["detected_at_ms"], 3 * STEP)
        self.assertEqual(pivot["confirmed_at_ms"], 5 * STEP)
        self.assertEqual(pivot["available_at_ms"], 5 * STEP)

    def test_configurable_pivot_window(self) -> None:
        result = self.run_engine([100, 105, 100], StructureConfig(left_bars=1, right_bars=1))
        pivot = next(e for e in result["events"] if e["kind"] == "swing_high")
        self.assertEqual(pivot["confirmed_at_ms"], 3 * STEP)

    def test_strict_ties_not_confirmed(self) -> None:
        result = self.run_engine([100, 105, 110, 110, 100])
        self.assertFalse(
            any(e["kind"] == "swing_high" and e["state"] == "confirmed" for e in result["events"])
        )

    def test_hh_hl_lh_ll_and_trend(self) -> None:
        result = self.run_engine(STRUCTURE_PRICES)
        kinds = {e["kind"] for e in result["events"]}
        self.assertTrue({"HH", "HL", "LL"}.issubset(kinds))
        inverse = self.run_engine([220 - p for p in STRUCTURE_PRICES])
        self.assertTrue({"LH", "LL", "HH"}.issubset({e["kind"] for e in inverse["events"]}))
        self.assertEqual(self.run_engine(STRUCTURE_PRICES[:11])["trend"], "alta")
        self.assertEqual(
            self.run_engine([220 - p for p in STRUCTURE_PRICES[:11]])["trend"], "baixa"
        )

    def test_bos_choch_and_false_break_lifecycle(self) -> None:
        result = self.run_engine(STRUCTURE_PRICES)
        bos = next(
            e for e in result["events"] if e["kind"] == "BOS" and e["event_time_ms"] == 10 * STEP
        )
        self.assertEqual(bos["confirmed_at_ms"], 12 * STEP)
        self.assertEqual(bos["state"], "invalidated")
        self.assertEqual(bos["invalidated_at_ms"], 13 * STEP)
        choch = next(e for e in result["events"] if e["kind"] == "CHoCH")
        self.assertEqual(choch["evidence"][0]["prior_trend"], "alta")
        self.assertEqual(choch["confirmed_at_ms"], 17 * STEP)
        self.assertEqual(choch["state"], "confirmed")
        self.assertTrue(any(e["kind"] == "false_break" for e in result["events"]))

    def test_first_break_without_prior_trend_is_bos(self) -> None:
        result = self.run_engine(STRUCTURE_PRICES[:7])
        bos = next(e for e in result["events"] if e["kind"] == "BOS")
        self.assertEqual(bos["evidence"][0]["prior_trend"], "indeterminado")
        self.assertEqual(bos["state"], "candidate")

    def test_flat_and_short_history_insufficient(self) -> None:
        result = self.run_engine([100] * 12)
        self.assertEqual(result["trend"], "indeterminado")
        self.assertTrue(result["insufficient_data"])
        self.assertEqual(result["levels"], [])

    def test_equal_extremes_describe_range(self) -> None:
        result = self.run_engine([100, 104, 100, 96] * 5)
        self.assertEqual(result["trend"], "lateralizacao")

    def test_gap_rejected(self) -> None:
        candles = prices(STRUCTURE_PRICES)
        with self.assertRaises(MarketError):
            analyze_structure(candles[:5] + candles[6:], INTERVAL, len(candles) * STEP)

    def test_invalid_config(self) -> None:
        with self.assertRaises(ValueError):
            StructureConfig(version="made_up_version")
        for kwargs in (
            {"right_bars": 0},
            {"left_bars": True},
            {"break_buffer": float("nan")},
            {"confirmation_closes": 0},
        ):
            with self.assertRaises(ValueError):
                StructureConfig(**kwargs)
