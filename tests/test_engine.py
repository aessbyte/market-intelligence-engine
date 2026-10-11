import copy
import unittest
from dataclasses import replace

from market_intelligence.engine import analyze, canonical_json
from market_intelligence.indicators import calculate
from market_intelligence.models import Interval, MarketError, Regime
from market_intelligence.regime import aggregate, classify
from market_intelligence.validation import parse_klines

from tests.fixtures import CUTOFF, rows, snapshot


class EngineTests(unittest.TestCase):
    def test_pipeline_simulated_and_deterministic(self) -> None:
        data = snapshot()
        before = copy.deepcopy(data)
        a, b = analyze(data), analyze(data)
        self.assertEqual(canonical_json(a), canonical_json(b))
        self.assertEqual(data, before)
        self.assertTrue(a["provenance"]["simulated"])
        self.assertEqual(a["status"], "ok")
        self.assertEqual(set(a["timeframes"]), {"H1", "H4", "D1"})
        self.assertFalse(any(s["probability"] is not None for s in a["scenarios"]))

    def test_all_regimes(self) -> None:
        for slope, regime in ((0.2, "alta"), (-0.2, "baixa"), (0, "lateralizacao")):
            with self.subTest(slope=slope):
                self.assertEqual(analyze(snapshot(slope))["regime"], regime)

    def test_unknown_and_conflicting_timeframes(self) -> None:
        f = calculate(parse_klines(rows(Interval.H1)))
        self.assertEqual(classify(replace(f, rsi14=50))[0], Regime.UNKNOWN)
        self.assertEqual(aggregate([Regime.BULL, Regime.BEAR, Regime.BULL]), Regime.UNKNOWN)
        self.assertEqual(aggregate([Regime.BULL, Regime.UNKNOWN, Regime.BULL]), Regime.UNKNOWN)

    def test_rule_threshold_boundary(self) -> None:
        f = calculate(parse_klines(rows(Interval.H1)))
        f = replace(f, ema_gap_atr=0.5, ema20_slope5_atr=0.05, rsi14=55)
        self.assertEqual(classify(f)[0], Regime.BULL)
        self.assertEqual(classify(replace(f, ema_gap_atr=0.49999))[0], Regime.UNKNOWN)

    def test_gap_missing_and_malformed_degrade(self) -> None:
        for problem in ("gap", "missing", "malformed", "fetch"):
            data = snapshot()
            if problem == "gap":
                del data["klines"]["H1"][50]
            elif problem == "missing":
                del data["klines"]["H1"]
            elif problem == "malformed":
                data["klines"]["H1"] = [[1]]
            else:
                data["fetch_errors"]["H1"] = "network unavailable"
            result = analyze(data)
            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["regime"], "indeterminado")
            self.assertIsNone(result["timeframes"]["H1"]["indicators"])

    def test_rejects_unlabeled_and_future_cutoffs(self) -> None:
        for change in (
            {"source": "unknown"},
            {"as_of_ms": CUTOFF + 1},
            {"as_of_ms": True},
            {"requested_bars": 99},
            {"klines": []},
            {"fetch_errors": []},
            {"symbol_info": {}},
            {"symbol": 123},
        ):
            data = snapshot()
            data.update(change)
            with self.assertRaises(MarketError):
                analyze(data)

    def test_extreme_finite_values_fail_safely(self) -> None:
        data = snapshot()
        for row in data["klines"]["H1"]:
            row[1] = row[3] = row[4] = "1e308"
            row[2] = "1.7e308"
        result = analyze(data)
        self.assertEqual(result["status"], "degraded")
        self.assertIsNone(result["timeframes"]["H1"]["indicators"])

    def test_appending_future_prices_cannot_change_features_or_regime(self) -> None:
        data = snapshot()
        original = analyze(data)
        for interval in Interval:
            future = rows(interval, 250, slope=1000, cutoff=CUTOFF + 250 * interval.milliseconds)
            data["klines"][interval.name].extend(future)
        result = analyze(data)
        for interval in Interval:
            a, b = original["timeframes"][interval.name], result["timeframes"][interval.name]
            self.assertEqual(a["indicators"], b["indicators"])
            self.assertEqual(a["regime"], b["regime"])

    def test_historical_prefix_matches_full_history_at_same_cutoff(self) -> None:
        for interval in Interval:
            full = rows(interval, count=350)
            cut = full[249][6] + 1
            from market_intelligence.validation import validate

            closed, report = validate(parse_klines(full), interval, cut)
            self.assertTrue(report.valid)
            self.assertEqual(calculate(closed), calculate(parse_klines(full[:250])))

    def test_historical_cross_timeframe_replay(self) -> None:
        data = snapshot()
        cutoff = CUTOFF - 3 * Interval.D1.milliseconds
        data["as_of_ms"] = cutoff
        data["requested_bars"] = 100
        for interval in Interval:
            data["klines"][interval.name] = rows(interval, count=100, cutoff=cutoff)
        result = analyze(data)
        self.assertEqual(result["status"], "ok")
        for f in result["timeframes"].values():
            self.assertLess(f["quality"]["last_close_ms"], cutoff)
