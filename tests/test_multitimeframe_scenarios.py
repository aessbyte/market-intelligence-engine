"""Scenario unit tests use explicit mocked module results, not market observations."""

import unittest

from market_intelligence.multitimeframe import compare_timeframes
from market_intelligence.scenarios import build_scenarios

from tests.fixtures import CUTOFF


def frames(trends: tuple[str, str, str], direction: str | None = None) -> dict:
    result = {}
    for name, trend in zip(("D1", "H4", "H1"), trends):
        event = (
            {
                "id": name + ":mock_bos",
                "kind": "BOS",
                "state": "confirmed",
                "confirmed_at_ms": CUTOFF,
                "available_at_ms": CUTOFF,
                "evidence": [{"direction": direction}],
            }
            if direction
            else None
        )
        result[name] = {
            "quality": {"valid": True},
            "regime": "indeterminado",
            "structure": {
                "trend": trend,
                "last_close": 100,
                "last_close_time_ms": CUTOFF - 1,
                "events": [event] if event else [],
                "event_journal": [event] if event else [],
                "levels": [
                    {
                        "kind": kind,
                        "price": price,
                        "event_id": name + kind,
                        "available_at_ms": CUTOFF - 1000,
                        "broken": False,
                    }
                    for kind, price in (("support", 95), ("resistance", 105))
                ],
            },
            "wyckoff": {"range": None, "events": [], "event_journal": [], "liquidity_warnings": []},
        }
    return result


class MultitimeframeScenarioTests(unittest.TestCase):
    def scenario(self, value: dict) -> list[dict]:
        comparison = compare_timeframes(value, CUTOFF)
        return build_scenarios(value, comparison, CUTOFF)

    def test_conflict_and_equal_weight(self) -> None:
        value = frames(("alta", "baixa", "indeterminado"))
        result = compare_timeframes(value, CUTOFF)
        self.assertEqual(result["structural_consensus"], "indeterminado")
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(result["policy"], "equal_evidence_weight_no_timeframe_is_truth")
        self.assertEqual([s["state"] for s in self.scenario(value)], ["awaiting_confirmation"] * 3)

    def test_active_bullish_without_d1_veto(self) -> None:
        result = self.scenario(frames(("indeterminado", "alta", "alta"), "up"))
        self.assertEqual(result[0]["state"], "active")
        self.assertTrue(all(c["met"] for c in result[0]["activation_conditions"]))
        self.assertTrue(result[0]["favorable_evidence"])
        self.assertTrue(result[0]["invalidation_conditions"])

    def test_active_bearish_and_opposing_scenario_invalidated(self) -> None:
        result = self.scenario(frames(("indeterminado", "baixa", "baixa"), "down"))
        self.assertEqual(result[1]["state"], "active")
        self.assertEqual(result[0]["state"], "invalidated")

    def test_directional_evidence_requires_freshness(self) -> None:
        value = frames(("alta", "alta", "alta"), "up")
        for f in value.values():
            f["structure"]["events"][0]["confirmed_at_ms"] = 1
        self.assertEqual(self.scenario(value)[0]["state"], "awaiting_confirmation")

    def test_h1_invalidation_price(self) -> None:
        value = frames(("alta", "alta", "alta"), "up")
        value["H1"]["structure"]["last_close"] = 94
        self.assertEqual(self.scenario(value)[0]["state"], "invalidated")

    def test_active_neutral_and_confirmed_range_break_invalidation(self) -> None:
        value = frames(("lateralizacao", "lateralizacao", "lateralizacao"))
        for name, f in value.items():
            f["wyckoff"]["range"] = {
                "id": name + "range",
                "lower": 95,
                "upper": 105,
                "state": "confirmed",
                "available_at_ms": CUTOFF,
                "breakout_direction": None,
            }
        self.assertEqual(self.scenario(value)[2]["state"], "active")
        for f in value.values():
            f["wyckoff"]["range"]["state"] = "invalidated"
            f["wyckoff"]["range"]["breakout_direction"] = "up"
        self.assertEqual(self.scenario(value)[2]["state"], "invalidated")

    def test_missing_timeframe_and_low_liquidity_defer(self) -> None:
        value = frames(("alta", "alta", "alta"), "up")
        value["D1"]["quality"]["valid"] = False
        self.assertEqual(self.scenario(value)[0]["state"], "awaiting_confirmation")
        self.assertIn("D1", self.scenario(value)[0]["insufficient_data"])
        value["D1"]["quality"]["valid"] = True
        value["H1"]["wyckoff"]["liquidity_warnings"] = [{"event_time_ms": CUTOFF - 3_600_000}]
        self.assertEqual(self.scenario(value)[0]["state"], "awaiting_confirmation")

    def test_future_event_is_rejected(self) -> None:
        value = frames(("alta", "alta", "alta"), "up")
        value["D1"]["structure"]["event_journal"][0]["available_at_ms"] = CUTOFF + 1
        with self.assertRaises(ValueError):
            compare_timeframes(value, CUTOFF)

    def test_no_probability_or_expected_return(self) -> None:
        for scenario in self.scenario(frames(("alta", "alta", "alta"), "up")):
            self.assertIsNone(scenario["probability"])
            self.assertEqual(scenario["forecast"]["status"], "unavailable")
            self.assertIsNone(scenario["forecast"]["calibrated_probability"])
            self.assertIsNone(scenario["forecast"]["expected_return_interval"])
