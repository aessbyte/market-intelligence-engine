import unittest
from dataclasses import replace

from market_intelligence.structure import analyze_structure
from market_intelligence.wyckoff import WyckoffConfig, analyze_wyckoff

from tests.task02_fixtures import (
    INTERVAL,
    SHORT_RANGE,
    SOS_LPS,
    SOW_LPSY,
    SPRING,
    STEP,
    UPTHRUST,
    prices,
    range_candles,
)


class WyckoffTests(unittest.TestCase):
    def analyze(self, tail: list[tuple], prior: str | None = None) -> dict:
        candles = range_candles(tail)
        structure = analyze_structure(candles, INTERVAL, len(candles) * STEP)
        if prior:
            structure["trend_history"] = [
                {"available_at_ms": c.close_time_ms + 1, "trend": prior} for c in candles
            ]
        return analyze_wyckoff(candles, INTERVAL, len(candles) * STEP, structure, SHORT_RANGE)

    def test_frozen_range_and_extreme_tests(self) -> None:
        result = self.analyze(SPRING)
        self.assertEqual(result["range"]["lower"], 95)
        self.assertEqual(result["range"]["upper"], 105)
        self.assertEqual(result["range"]["state"], "confirmed")
        self.assertTrue(any(e["kind"] == "range_lower_test" for e in result["events"]))

    def test_spring_upthrust_confirmation(self) -> None:
        for tail, kind in ((SPRING, "Spring"), (UPTHRUST, "Upthrust")):
            with self.subTest(kind=kind):
                candidate = next(e for e in self.analyze(tail[:1])["events"] if e["kind"] == kind)
                self.assertEqual(candidate["state"], "candidate")
                confirmed = next(e for e in self.analyze(tail)["events"] if e["kind"] == kind)
                self.assertEqual(confirmed["confirmed_at_ms"], 14 * STEP)
                self.assertEqual(confirmed["state"], "confirmed")
                self.assertEqual(confirmed["evidence"][0]["observation"], "sweep_and_close_inside")

    def test_spring_and_upthrust_invalidation(self) -> None:
        for tail, extra, kind in (
            (SPRING, (96, 97, 90, 92, 10), "Spring"),
            (UPTHRUST, (104, 110, 103, 108, 10), "Upthrust"),
        ):
            result = self.analyze(tail + [extra])
            event = next(e for e in result["events"] if e["kind"] == kind)
            self.assertEqual(event["state"], "invalidated")
            self.assertEqual(event["invalidated_at_ms"], 15 * STEP)

    def test_sos_sow_lps_lpsy_with_followthrough(self) -> None:
        for tail, kind, retest in ((SOS_LPS, "SOS", "LPS"), (SOW_LPSY, "SOW", "LPSY")):
            result = self.analyze(tail)
            for name in (kind, retest):
                event = next(e for e in result["events"] if e["kind"] == name)
                self.assertEqual(event["state"], "confirmed")
            self.assertEqual(result["range"]["state"], "invalidated")
            candidate = next(e for e in self.analyze(tail[:3])["events"] if e["kind"] == retest)
            self.assertEqual(candidate["state"], "candidate")

    def test_lps_lpsy_invalidation(self) -> None:
        for tail, extra, kind in (
            (SOS_LPS, (104, 105, 99, 100, 10), "LPS"),
            (SOW_LPSY, (96, 101, 95, 100, 10), "LPSY"),
        ):
            event = next(e for e in self.analyze(tail + [extra])["events"] if e["kind"] == kind)
            self.assertEqual(event["state"], "invalidated")

    def test_no_lps_without_confirmed_strength_break(self) -> None:
        result = self.analyze(SPRING)
        self.assertFalse(any(e["kind"] in ("LPS", "LPSY") for e in result["events"]))

    def test_hypotheses_remain_interpretations(self) -> None:
        for tail, prior, interpretation in (
            (SPRING, "alta", "reaccumulation"),
            (UPTHRUST, "baixa", "redistribution"),
            (SPRING, None, "accumulation"),
            (UPTHRUST, None, "distribution"),
        ):
            h = self.analyze(tail, prior)["hypotheses"][0]
            self.assertEqual(h["interpretation"], interpretation)
            self.assertEqual(h["state"], "candidate")
            self.assertIsNone(h["phase"])

    def test_low_liquidity_does_not_confirm_signal(self) -> None:
        tail = [(*SPRING[0][:4], 0), SPRING[1]]
        result = self.analyze(tail)
        event = next(e for e in result["events"] if e["kind"] == "Spring")
        self.assertEqual(event["state"], "candidate")
        self.assertTrue(result["liquidity_warnings"])

    def test_weak_volume_sos_stays_candidate(self) -> None:
        tail = [(*SOS_LPS[0][:4], 2), SOS_LPS[1]]
        event = next(e for e in self.analyze(tail)["events"] if e["kind"] == "SOS")
        self.assertEqual(event["state"], "candidate")

    def test_followthrough_timeout(self) -> None:
        result = self.analyze(SPRING[:1] + [(99, 100, 98, 99, 10)] * 8)
        event = next(e for e in result["events"] if e["kind"] == "Spring")
        self.assertEqual(event["state"], "invalidated")
        self.assertEqual(event["evidence"][-1]["reason"], "follow_through_timeout")

    def test_no_range_without_evidence_or_liquidity(self) -> None:
        for data in (
            prices([100] * 30),
            prices(list(range(100, 130))),
            tuple(replace(c, volume=0, trades=0, quote_volume=0) for c in range_candles([])),
        ):
            structure = analyze_structure(data, INTERVAL, len(data) * STEP)
            result = analyze_wyckoff(data, INTERVAL, len(data) * STEP, structure, SHORT_RANGE)
            self.assertIsNone(result["range"])
            self.assertTrue(result["insufficient_data"])

    def test_invalid_config(self) -> None:
        with self.assertRaises(ValueError):
            WyckoffConfig(version="made_up_version")
        for kwargs in (
            {"range_lookback": 2},
            {"signal_window": False},
            {"max_efficiency": float("nan")},
            {"min_quote_volume": -1},
        ):
            with self.assertRaises(ValueError):
                WyckoffConfig(**kwargs)
