"""ASGI integration with explicitly labelled synthetic replay; never public live claims."""

from pathlib import Path
import json
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from market_intelligence.web import create_app
from market_intelligence.web.config import WebConfig
from market_intelligence.web.service import AnalysisService

from tests.test_web_contract import synthetic_snapshot


class WebAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        snapshot = Path(self.temporary.name) / "synthetic.json"
        snapshot.write_text(json.dumps(synthetic_snapshot()))
        self.config = WebConfig(replay_snapshot=snapshot)
        self.service = AnalysisService(self.config)
        self.client = TestClient(create_app(service=self.service))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def completed(self, symbol: str = "BTCUSDT") -> dict:
        response = self.client.post("/api/v1/analyses", json={"symbol": symbol})
        self.assertEqual(response.status_code, 202)
        job = response.json()
        for _ in range(100):
            job = self.client.get("/api/v1/jobs/" + job["job_id"]).json()
            if job["status"] in ("completed", "failed"):
                return job
            time.sleep(0.03)
        self.fail("job did not finish")

    def test_health_openapi_and_versioned_contract(self) -> None:
        health = self.client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["mode"], "replay")
        self.assertFalse(health.json()["training_available"])
        schema = self.client.get("/openapi.json").json()
        self.assertIn("CompactAnalysis", schema["components"]["schemas"])
        self.assertIn("/api/v1/analyses", schema["paths"])

    def test_submission_poll_result_and_all_projections(self) -> None:
        job = self.completed()
        self.assertEqual(job["status"], "completed")
        base = "/api/v1/analyses/" + job["result_id"]
        envelope = self.client.get(base)
        self.assertEqual(envelope.status_code, 200)
        self.assertEqual(envelope.json()["api_version"], "1")
        self.assertTrue(envelope.json()["analysis"]["provenance"]["simulated"])
        for section in (
            "ohlcv",
            "indicators",
            "diagnostic",
            "structure",
            "wyckoff",
            "scenarios",
            "predictions",
            "model-quality",
        ):
            response = self.client.get(base + "/" + section)
            self.assertEqual(response.status_code, 200, section)
            self.assertEqual(response.json()["analysis_id"], job["result_id"])
        full = self.client.get(base + "/engine").json()
        self.assertEqual(full["schema_version"], "3")
        self.assertIn("event_journal", full["timeframes"]["H1"]["structure"])
        self.assertNotIn(
            "event_journal", envelope.json()["analysis"]["timeframes"]["H1"]["structure"]
        )

    def test_input_validation_rejects_symbols_parameters_and_extra_fields(self) -> None:
        for payload in (
            {"symbol": "../etc/passwd"},
            {"symbol": "BTC USDT"},
            {"symbol": "BTCUSDT", "bars": 99},
            {"symbol": "BTCUSDT", "bars": True},
            {"symbol": "BTCUSDT", "bars": 501},
            {"symbol": "BTCUSDT", "market": "binance_private"},
            {"symbol": "BTCUSDT", "api_key": "never-accepted"},
        ):
            response = self.client.post("/api/v1/analyses", json=payload)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
            self.assertIn("request_id", response.json()["error"])

    def test_unavailable_forecasts_are_null_not_numeric_fallbacks(self) -> None:
        job = self.completed()
        result = self.client.get("/api/v1/analyses/" + job["result_id"]).json()
        self.assertEqual(
            [prediction["horizon_days"] for prediction in result["analysis"]["predictions"]],
            [7, 30, 90],
        )
        for prediction in result["analysis"]["predictions"]:
            self.assertIsNone(prediction["probabilities"])
            self.assertIsNone(prediction["return_distribution"])

    def test_symbol_discovery_and_unknown_futures_are_distinguished(self) -> None:
        known = self.client.get("/api/v1/symbol-validation/btcusdt").json()
        self.assertTrue(known["valid"])
        self.assertEqual(known["symbol"], "BTCUSDT")
        self.assertIsNone(known["markets"][1]["available"])
        self.assertFalse(known["markets"][1]["supported"])
        self.assertEqual(
            self.client.get("/api/v1/symbols?q=BTC").json()["symbols"][0]["symbol"], "BTCUSDT"
        )
        self.assertEqual(self.client.get("/api/v1/symbols?exact=ETHUSDT").json()["symbols"], [])

    def test_unknown_token_fails_without_a_result(self) -> None:
        job = self.completed("WRONGUSDT")
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"]["code"], "SYMBOL_UNAVAILABLE")
        self.assertIsNone(job["result_id"])

    def test_futures_and_weekly_candles_are_explicitly_unavailable(self) -> None:
        response = self.client.post(
            "/api/v1/analyses", json={"symbol": "BTCUSDT", "market": "futures"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "MARKET_UNSUPPORTED")
        job = self.completed()
        response = self.client.get("/api/v1/analyses/" + job["result_id"] + "/ohlcv?interval=W1")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "TIMEFRAME_UNAVAILABLE")

    def test_cors_security_headers_and_no_admin_endpoints(self) -> None:
        response = self.client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("x-request-id", response.headers)
        rejected = self.client.get(
            "/api/v1/health", headers={"Origin": "https://untrusted.example"}
        )
        self.assertNotIn("access-control-allow-origin", rejected.headers)
        for path in ("/api/v1/train", "/api/v1/execute", "/api/v1/orders"):
            response = self.client.post(path, json={})
            self.assertEqual(response.status_code, 404)

    def test_expired_and_unknown_ids_have_typed_errors(self) -> None:
        for path in ("/api/v1/jobs/missing", "/api/v1/analyses/missing"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertIn("code", response.json()["error"])

    def test_request_body_is_bounded_before_json_parsing(self) -> None:
        response = self.client.post("/api/v1/analyses", json={"symbol": "B" * 9000})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "PAYLOAD_TOO_LARGE")
        self.assertIn("request_id", response.json()["error"])
        response = self.client.post(
            "/api/v1/analyses",
            content=iter([b'{"symbol":"', b"B" * 4096, b"B" * 4096, b'"}']),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "PAYLOAD_TOO_LARGE")

    def test_spa_assets_cannot_turn_unknown_api_paths_into_html(self) -> None:
        dist = Path(self.temporary.name) / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>synthetic test shell</html>")
        app = create_app(
            config=WebConfig(replay_snapshot=self.config.replay_snapshot, frontend_dist=dist)
        )
        with TestClient(app) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/dashboard").status_code, 200)
            missing = client.get("/api/v1/nonexistent")
            self.assertEqual(missing.status_code, 404)
            self.assertIn("application/json", missing.headers["content-type"])
            self.assertEqual(client.get("/../secret.json").status_code, 200)
            self.assertNotIn("secret", client.get("/../secret.json").text)
            self.assertEqual(client.get("/%2e%2e/secret.json").status_code, 404)


if __name__ == "__main__":
    unittest.main()
