"""Offline presentation and service contracts. Synthetic inputs are never real evidence."""

from copy import deepcopy
from pathlib import Path
import json
import tempfile
import threading
import time
import unittest

from market_intelligence.binance import BinanceClient
from market_intelligence.engine import analyze, canonical_json
from market_intelligence.indicators import calculate
from market_intelligence.models import Interval, MarketError
from market_intelligence.validation import parse_klines
from market_intelligence.web.adapter import compact_analysis, model_quality
from market_intelligence.web.config import WebConfig
from market_intelligence.web.contracts import AnalysisRequest, CompactAnalysis
from market_intelligence.web.service import AnalysisService, ServiceError

ROOT = Path(__file__).resolve().parents[1]


def synthetic_snapshot() -> dict:
    return json.loads((ROOT / "examples/task02-synthetic-snapshot.json").read_text())


def await_job(service: AnalysisService, job_id: str) -> dict:
    for _ in range(200):
        job = service.job(job_id)
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("test analysis did not complete")


class WebContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = synthetic_snapshot()
        cls.engine = json.loads(canonical_json(analyze(cls.snapshot, result_version=3)))
        cls.compact = compact_analysis(
            "test-analysis",
            cls.snapshot,
            cls.engine,
            "replay",
            model_quality(None, "BTCUSDT"),
            1000,
            ["DADOS SIMULADOS: teste explicitamente identificado."],
        )

    def test_engine_scalars_and_current_events_are_unchanged(self) -> None:
        restored = deepcopy(self.compact["analysis"])
        for name in ("H1", "H4", "D1"):
            for module in ("structure", "wyckoff"):
                restored["timeframes"][name][module]["event_journal"] = self.engine["timeframes"][
                    name
                ][module]["event_journal"]
            restored["timeframes"][name]["structure"]["trend_history"] = self.engine["timeframes"][
                name
            ]["structure"]["trend_history"]
        self.assertEqual(restored, self.engine)

    def test_chart_uses_original_prices_timestamps_and_engine_indicators(self) -> None:
        for name in ("H1", "H4", "D1"):
            candles = parse_klines(self.snapshot["klines"][name])
            chart = self.compact["charts"][name]
            self.assertEqual(chart["candles"][-1]["time_ms"], candles[-1].open_time_ms)
            self.assertEqual(chart["candles"][-1]["close"], candles[-1].close)
            calculated = calculate(candles)
            self.assertEqual(chart["ema20"][-1]["value"], calculated.ema20)
            self.assertEqual(chart["ema50"][-1]["value"], calculated.ema50)
            self.assertEqual(chart["rsi14"][-1]["value"], calculated.rsi14)

    def test_event_confirmation_is_not_replaced_by_historical_position(self) -> None:
        events = self.compact["charts"]["H1"]["events"]
        confirmed = [event for event in events if event["confirmed_at_ms"] is not None]
        self.assertTrue(confirmed)
        self.assertTrue(
            any(event["confirmed_at_ms"] > event["event_time_ms"] for event in confirmed)
        )
        for event in events:
            self.assertLessEqual(event["available_at_ms"], self.engine["as_of_ms"])
            self.assertGreater(event["detected_at_ms"], event["event_time_ms"])

    def test_absent_probabilities_remain_null(self) -> None:
        for prediction in self.compact["analysis"]["predictions"]:
            self.assertIsNone(prediction["probabilities"])
            self.assertIsNone(prediction["return_distribution"])
            self.assertEqual(prediction["status"], "INSUFFICIENT_EVIDENCE")

    def test_compact_contract_rejects_nonfinite_reference_and_extra_keys(self) -> None:
        broken = deepcopy(self.compact)
        broken["summary"]["reference_price"] = float("nan")
        with self.assertRaises(ValueError):
            CompactAnalysis.model_validate(broken)
        broken = deepcopy(self.compact)
        broken["invented_probability"] = 0.5
        with self.assertRaises(ValueError):
            CompactAnalysis.model_validate(broken)

    def test_short_valid_history_remains_chartable_but_not_analyzed(self) -> None:
        snapshot = synthetic_snapshot()
        for interval in Interval:
            snapshot["klines"][interval.name] = snapshot["klines"][interval.name][-5:]
        result = json.loads(canonical_json(analyze(snapshot, result_version=3)))
        compact = compact_analysis(
            "short", snapshot, result, "replay", model_quality(None, "BTCUSDT"), 0, []
        )
        self.assertEqual(compact["summary"]["quality"], "degraded")
        for name in ("H1", "H4", "D1"):
            self.assertEqual(len(compact["charts"][name]["candles"]), 5)
            self.assertIsNone(compact["analysis"]["timeframes"][name]["indicators"])
            self.assertEqual(compact["charts"][name]["ema20"], [])

    def test_invalid_chart_data_is_not_sorted_or_filled(self) -> None:
        snapshot = synthetic_snapshot()
        snapshot["klines"]["H1"].pop(-3)
        result = json.loads(canonical_json(analyze(snapshot, result_version=3)))
        compact = compact_analysis(
            "gap", snapshot, result, "replay", model_quality(None, "BTCUSDT"), 0, []
        )
        self.assertEqual(compact["charts"]["H1"]["candles"], [])
        self.assertTrue(any("gap" in warning for warning in compact["warnings"]))

    def test_change_is_previous_hourly_close_not_claimed_24_hours(self) -> None:
        candles = self.compact["charts"]["H1"]["candles"]
        expected = 100 * (candles[-1]["close"] / candles[-2]["close"] - 1)
        self.assertEqual(self.compact["summary"]["change_percent"], expected)
        self.assertEqual(self.compact["summary"]["change_basis"], "previous_closed_H1")

    def test_quote_and_tick_metadata_come_from_exchange_not_symbol_guessing(self) -> None:
        snapshot = synthetic_snapshot()
        snapshot["symbol_info"].update(
            {
                "baseAsset": "ETH",
                "quoteAsset": "BTC",
                "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.00000100"}],
            }
        )
        adapted = compact_analysis(
            "metadata", snapshot, self.engine, "replay", model_quality(None, "BTCUSDT"), 0, []
        )
        self.assertEqual(adapted["summary"]["quote_asset"], "BTC")
        self.assertEqual(adapted["summary"]["base_asset"], "ETH")
        self.assertEqual(adapted["summary"]["tick_size"], 0.000001)
        self.assertIsNone(self.compact["summary"]["quote_asset"])

    def test_unsupported_symbol_does_not_reuse_btc_model_quality(self) -> None:
        bundle = json.loads((ROOT / "examples/task03-btc-model.json").read_text())
        self.assertFalse(model_quality(bundle, "ETHUSDT").configured)
        quality = model_quality(bundle, "BTCUSDT")
        self.assertTrue(quality.configured)
        self.assertEqual(quality.horizons["7"].model_kind, "frequency")
        final = bundle["report"]["horizons"]["7"]["folds"][-1]
        self.assertEqual(
            quality.horizons["7"].final_test_end_ms,
            final["split_metadata"]["test"]["last_origin_ms"],
        )
        self.assertNotEqual(
            quality.horizons["7"].final_test_end_ms, final["boundaries"]["test_end_ms"]
        )
        self.assertEqual(
            quality.horizons["7"].final_test_metrics, final["test_metrics"]["frequency"]
        )

    def test_configuration_requires_explicit_cors_and_paired_artifacts(self) -> None:
        with self.assertRaises(ValueError):
            WebConfig(cors_origins=("*",))
        with self.assertRaises(ValueError):
            WebConfig(model_bundle=Path("model.json"))
        with self.assertRaises(ValueError):
            WebConfig(workers=100)


class WebServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        path = Path(self.temporary.name) / "simulated.json"
        path.write_text(json.dumps(synthetic_snapshot()))
        self.path = path

    def service(self, **settings: object) -> AnalysisService:
        service = AnalysisService(WebConfig(replay_snapshot=self.path, **settings))  # type: ignore[arg-type]
        self.addCleanup(service.shutdown)
        return service

    def test_replay_is_explicit_and_never_queries_network(self) -> None:
        service = self.service()
        job = await_job(
            service, service.submit(AnalysisRequest(symbol="BTCUSDT"), "req", "offline")["job_id"]
        )
        self.assertEqual(job["status"], "completed")
        result = service.result(job["result_id"])
        self.assertEqual(result["mode"], "replay")
        self.assertTrue(result["analysis"]["provenance"]["simulated"])
        self.assertTrue(any("SIMULADOS" in warning for warning in result["warnings"]))
        self.assertEqual(
            service.result(job["result_id"], full=True),
            json.loads(canonical_json(analyze(synthetic_snapshot(), result_version=3))),
        )

    def test_cache_does_not_recompute_or_modify_engine(self) -> None:
        service = self.service()
        request = AnalysisRequest(symbol="BTCUSDT")
        first = await_job(service, service.submit(request, "r1", "offline")["job_id"])
        before = service.result(first["result_id"], full=True)
        cached = service.submit(request, "r2", "offline")
        self.assertEqual(cached["status"], "completed")
        self.assertEqual(cached["result_id"], first["result_id"])
        self.assertTrue(service.result(first["result_id"])["cache"]["hit"])
        self.assertEqual(service.result(first["result_id"], full=True), before)

    def test_expiry_removes_results_and_jobs(self) -> None:
        now = [0.0]
        service = AnalysisService(
            WebConfig(replay_snapshot=self.path, cache_seconds=1, retention_seconds=2),
            clock=lambda: now[0],
        )
        self.addCleanup(service.shutdown)
        completed = await_job(
            service, service.submit(AnalysisRequest(symbol="BTCUSDT"), "req", "offline")["job_id"]
        )
        now[0] = 3
        with self.assertRaises(ServiceError) as result_error:
            service.result(completed["result_id"])
        self.assertEqual(result_error.exception.status_code, 404)
        with self.assertRaises(ServiceError):
            service.job(completed["job_id"])

    def test_unknown_replay_symbol_is_failure_not_fixture_substitution(self) -> None:
        service = self.service()
        job = await_job(
            service, service.submit(AnalysisRequest(symbol="ETHUSDT"), "req", "offline")["job_id"]
        )
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"]["code"], "SYMBOL_UNAVAILABLE")
        self.assertIsNone(job["result_id"])

    def test_futures_is_rejected_and_never_sent_to_spot_engine(self) -> None:
        service = self.service()
        with self.assertRaises(ServiceError) as rejected:
            service.submit(AnalysisRequest(symbol="BTCUSDT", market="futures"), "req", "offline")
        self.assertEqual(rejected.exception.code, "MARKET_UNSUPPORTED")

    def test_cheap_polling_does_not_consume_analysis_rate_budget(self) -> None:
        service = self.service(request_limit=1)
        job = await_job(
            service, service.submit(AnalysisRequest(symbol="BTCUSDT"), "req", "offline")["job_id"]
        )
        for _ in range(5):
            self.assertEqual(service.job(job["job_id"])["status"], "completed")
        with self.assertRaises(ServiceError) as rejected:
            service.submit(AnalysisRequest(symbol="BTCUSDT"), "req2", "offline")
        self.assertEqual(rejected.exception.code, "RATE_LIMITED")

    def test_queue_is_bounded_and_source_failure_never_activates_simulation(self) -> None:
        release = threading.Event()

        class UnavailableProvider(BinanceClient):
            def snapshot(self, *args: object, **kwargs: object) -> dict:
                release.wait(2)
                raise MarketError("temporary provider outage")

        service = AnalysisService(WebConfig(max_pending=1), client=UnavailableProvider())
        self.addCleanup(service.shutdown)
        try:
            jobs = [
                service.submit(AnalysisRequest(symbol="BTCUSDT"), "req", "offline")
                for _ in range(3)
            ]
            with self.assertRaises(ServiceError) as rejected:
                service.submit(AnalysisRequest(symbol="BTCUSDT"), "req", "offline")
            self.assertEqual(rejected.exception.code, "SERVICE_BUSY")
        finally:
            release.set()
        for job in jobs:
            failed = await_job(service, job["job_id"])
            self.assertEqual(failed["error"]["code"], "SOURCE_UNAVAILABLE")
            self.assertIsNone(failed["result_id"])

    def test_capacity_eviction_is_bounded_and_prefers_least_recently_used(self) -> None:
        class SyntheticProvider(BinanceClient):
            def snapshot(self, symbol: str, *args: object, **kwargs: object) -> dict:
                fixture = synthetic_snapshot()
                fixture["symbol"] = symbol
                fixture["symbol_info"]["symbol"] = symbol
                return fixture

        now = [0.0]
        service = AnalysisService(
            WebConfig(max_records=2), client=SyntheticProvider(), clock=lambda: now[0]
        )
        self.addCleanup(service.shutdown)
        first = await_job(
            service, service.submit(AnalysisRequest(symbol="AAAUSDT"), "req", "offline")["job_id"]
        )
        now[0] = 1
        second = await_job(
            service, service.submit(AnalysisRequest(symbol="BBBUSDT"), "req", "offline")["job_id"]
        )
        now[0] = 2
        service.result(first["result_id"])
        now[0] = 3
        third = await_job(
            service, service.submit(AnalysisRequest(symbol="CCCUSDT"), "req", "offline")["job_id"]
        )
        self.assertEqual(third["status"], "completed")
        self.assertEqual(len(service._records), 2)
        self.assertEqual(len(service._jobs), 2)
        self.assertEqual(service.result(first["result_id"])["summary"]["symbol"], "AAAUSDT")
        with self.assertRaises(ServiceError):
            service.result(second["result_id"])

    def test_serialized_cache_budget_rejects_without_truncating_results(self) -> None:
        service = self.service(max_cache_bytes=1024)
        job = await_job(
            service, service.submit(AnalysisRequest(symbol="BTCUSDT"), "req", "offline")["job_id"]
        )
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"]["code"], "SERVICE_BUSY")
        self.assertIsNone(job["result_id"])
        self.assertEqual(service._records, {})


if __name__ == "__main__":
    unittest.main()
