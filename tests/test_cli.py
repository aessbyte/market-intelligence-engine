import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_intelligence.cli import main

from tests.fixtures import snapshot


class CLITests(unittest.TestCase):
    def test_live_cli_with_explicitly_simulated_transport_result(self) -> None:
        out = io.StringIO()
        with (
            patch("market_intelligence.cli.BinanceClient.snapshot", return_value=snapshot()),
            contextlib.redirect_stdout(out),
        ):
            code = main(["analyze", "BTCUSDT"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())["provenance"]["simulated"])

    def test_replay_output_and_degraded_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "snapshot.json", Path(tmp) / "result.json"
            data = snapshot()
            source.write_text(json.dumps(data))
            self.assertEqual(main(["replay", str(source), "--output", str(target)]), 0)
            self.assertEqual(json.loads(target.read_text())["status"], "ok")
            del data["klines"]["D1"]
            source.write_text(json.dumps(data))
            self.assertEqual(main(["replay", str(source), "--output", str(target)]), 2)

    def test_errors_are_json_on_stderr(self) -> None:
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = main(["replay", "/nonexistent/snapshot.json"])
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(err.getvalue()))
        self.assertEqual(out.getvalue(), "")

    def test_naive_cutoff_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["analyze", "BTCUSDT", "--as-of", "2026-01-01T00:00:00"])
