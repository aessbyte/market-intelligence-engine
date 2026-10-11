import contextlib
import io
import json
import unittest
from importlib.resources import files

import jsonschema

from market_intelligence.cli import main
from market_intelligence.config import AnalysisConfig
from market_intelligence.engine import analyze, canonical_json
from market_intelligence.models import MarketError
from market_intelligence.models import Interval
from market_intelligence.render import render_text

from tests.fixtures import snapshot
from tests.fixtures import CUTOFF, rows


class Task02IntegrationTests(unittest.TestCase):
    def test_original_snapshot_exact_legacy_replay(self) -> None:
        with open("examples/btc-snapshot.json") as f:
            data = json.load(f)
        with open("examples/btc-analysis.json") as f:
            expected = json.load(f)
        self.assertEqual(analyze(data, result_version=1), expected)
        schema = json.loads(
            files("market_intelligence").joinpath("result-v1.schema.json").read_text()
        )
        jsonschema.validate(json.loads(canonical_json(expected)), schema)

    def test_v2_real_saved_snapshot_has_all_modules(self) -> None:
        with open("examples/btc-snapshot.json") as f:
            result = analyze(json.load(f))
        self.assertEqual(result["schema_version"], "2")
        for name in ("D1", "H4", "H1"):
            self.assertIsInstance(result["timeframes"][name]["structure"], dict)
            self.assertIsInstance(result["timeframes"][name]["wyckoff"], dict)
        self.assertEqual(
            [s["name"] for s in result["scenarios"]], ["bullish", "bearish", "neutral"]
        )
        schema = json.loads(files("market_intelligence").joinpath("result.schema.json").read_text())
        self.assertFalse(
            list(
                jsonschema.Draft202012Validator(schema).iter_errors(
                    json.loads(canonical_json(result))
                )
            )
        )

    def test_degraded_frame_does_not_produce_events(self) -> None:
        data = snapshot()
        del data["klines"]["H4"][20]
        result = analyze(data)
        self.assertIsNone(result["timeframes"]["H4"]["structure"])
        self.assertIsNone(result["timeframes"]["H4"]["wyckoff"])
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(all(s["state"] != "active" for s in result["scenarios"]))

    def test_future_candles_cannot_change_integrated_structure_or_scenarios(self) -> None:
        data = snapshot()
        before = analyze(data)
        for interval in Interval:
            data["klines"][interval.name] += rows(
                interval, count=25, slope=1000, cutoff=CUTOFF + 25 * interval.milliseconds
            )
        after = analyze(data)
        for name in ("H1", "H4", "D1"):
            for key in ("structure", "wyckoff"):
                self.assertEqual(before["timeframes"][name][key], after["timeframes"][name][key])
        self.assertEqual(before["multitimeframe"], after["multitimeframe"])
        self.assertEqual(before["scenarios"], after["scenarios"])

    def test_text_cli_and_legacy_option(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["replay", "examples/btc-snapshot.json", "--format", "text"]), 0)
        text = out.getvalue()
        for phrase in (
            "BTCUSDT",
            "D1:",
            "H4:",
            "H1:",
            "Cenario bullish",
            "Cenario bearish",
            "Cenario neutral",
            "Ativacao:",
            "Invalidacao:",
            "indisponiveis",
        ):
            self.assertIn(phrase, text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(
                main(["replay", "examples/btc-snapshot.json", "--schema-version", "1"]), 0
            )
        self.assertEqual(json.loads(out.getvalue())["schema_version"], "1")

    def test_configuration_validation_and_determinism(self) -> None:
        config = AnalysisConfig.from_dict(
            {"structure": {"left_bars": 3, "right_bars": 4}, "scenario_freshness_bars": 20}
        )
        data = snapshot()
        self.assertEqual(analyze(data, config), analyze(data, config))
        self.assertEqual(
            analyze(data, config)["configuration"]["analysis"]["structure"]["right_bars"], 4
        )
        for bad in (
            [],
            {"unknown": 1},
            {"structure": {"right_bars": -1}},
            {"wyckoff": {"made_up_rule": 1}},
            {"scenario_freshness_bars": True},
        ):
            with self.assertRaises(MarketError):
                AnalysisConfig.from_dict(bad)

    def test_text_renderer_degraded(self) -> None:
        data = snapshot()
        del data["klines"]["D1"]
        self.assertIn("D1: dados indisponiveis", render_text(analyze(data)))

    def test_schema_forbids_arbitrary_forecast_slots(self) -> None:
        result = analyze(snapshot())
        result["scenarios"][0]["forecast"]["calibrated_probability"] = 0.99
        schema = json.loads(files("market_intelligence").joinpath("result.schema.json").read_text())
        self.assertTrue(list(jsonschema.Draft202012Validator(schema).iter_errors(result)))
