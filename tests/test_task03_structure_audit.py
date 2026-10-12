"""Regression tests for confirmed audit defects, using synthetic prices only."""

import unittest
from dataclasses import replace

from market_intelligence.structure import StructureConfig, analyze_structure

from tests.task02_fixtures import INTERVAL, STEP, prices


class StructureAuditTests(unittest.TestCase):
    def timeout_history(self) -> tuple:
        candles = list(prices([100, 105, 110, 105, 100, 112, 111.05, 111.05, 112, 112, 112]))
        for index in range(5, len(candles)):
            candles[index] = replace(candles[index], high=115, low=99)
        return tuple(candles)

    def multiple_false_break_history(self) -> tuple:
        candles = list(prices([100, 105, 110, 105, 100, 116, 117, 114, 122, 123, 109]))
        candles[5] = replace(candles[5], high=120)
        return tuple(candles)

    def test_timeout_releases_level_and_allows_later_confirmation(self) -> None:
        candles = self.timeout_history()
        config = StructureConfig(confirmation_closes=3, false_break_window=2)
        at_timeout = analyze_structure(candles[:8], INTERVAL, 8 * STEP, config)
        self.assertFalse(at_timeout["levels"][0]["broken"])
        final = analyze_structure(candles, INTERVAL, len(candles) * STEP, config)
        events = [event for event in final["events"] if event["kind"] == "BOS"]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["state"], "invalidated")
        self.assertEqual(events[0]["evidence"][-1]["reason"], "confirmation_timeout")
        self.assertEqual(events[1]["state"], "confirmed")
        self.assertEqual(events[1]["confirmed_at_ms"], 11 * STEP)

    def test_multiple_level_returns_preserve_both_observations(self) -> None:
        candles = self.multiple_false_break_history()
        result = analyze_structure(candles, INTERVAL, len(candles) * STEP)
        observations = [event for event in result["events"] if event["kind"] == "false_break"]
        self.assertEqual(len(observations), 2)
        self.assertEqual({event["price"] for event in observations}, {111, 120})
        self.assertEqual(len({event["id"] for event in observations}), 2)
        self.assertEqual(len({event["evidence"][0]["break_id"] for event in observations}), 2)

    def test_two_sided_wick_preserves_both_candidates(self) -> None:
        candles = list(prices([100, 105, 110, 105, 100, 104, 105, 103, 102, 104, 103]))
        candles[-1] = replace(candles[-1], high=120, low=80)
        result = analyze_structure(tuple(candles), INTERVAL, len(candles) * STEP)
        observations = [
            event
            for event in result["events"]
            if event["kind"] == "possible_false_break"
            and event["event_time_ms"] == candles[-1].open_time_ms
        ]
        self.assertEqual(len(observations), 2)
        self.assertEqual(len({event["id"] for event in observations}), 2)
        self.assertEqual(
            {event["evidence"][0]["direction"] for event in observations}, {"up", "down"}
        )

    def test_audit_regressions_preserve_every_prefix(self) -> None:
        for candles, config in (
            (self.timeout_history(), StructureConfig(confirmation_closes=3, false_break_window=2)),
            (self.multiple_false_break_history(), StructureConfig()),
        ):
            complete = analyze_structure(candles, INTERVAL, len(candles) * STEP, config)
            for length in range(1, len(candles) + 1):
                cutoff = length * STEP
                prefix = analyze_structure(candles[:length], INTERVAL, cutoff, config)
                visible = [
                    event
                    for event in complete["event_journal"]
                    if event["available_at_ms"] <= cutoff
                ]
                self.assertEqual(prefix["event_journal"], visible)
