import os
import sys
import unittest
from importlib import reload
from pathlib import Path
from unittest import mock
import tempfile

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class SmokeSteps(unittest.TestCase):
    def setUp(self):
        # Force mock mode for offline tests
        os.environ["MOCK_MODE"] = "1"
        # Ensure we don't leave logs lying around from prior runs
        for fname in ["bot_logs.csv", "bot_metrics.csv"]:
            path = ROOT / fname
            if path.exists():
                path.unlink()

    def tearDown(self):
        os.environ.pop("MOCK_MODE", None)
        # Clean up any logs created during tests
        for fname in ["bot_logs.csv", "bot_metrics.csv"]:
            path = ROOT / fname
            if path.exists():
                path.unlink()

    def test_step2_runs_in_mock_mode(self):
        import api.bot_step2_keywords as step2
        reload(step2)
        step2.main()  # should not raise

    def test_step3_runs_in_mock_mode_with_decline(self):
        import api.bot_step3_replies as step3
        reload(step3)
        # Redirect logging to a temp file to avoid polluting repo
        with tempfile.TemporaryDirectory() as tmpdir:
            step3.LOG_PATH = Path(tmpdir) / "log.csv"
            with mock.patch("builtins.input", return_value="n"):
                step3.main()  # should not raise even though it prompts
            self.assertFalse((ROOT / "bot_logs.csv").exists())

    def test_no_gitignored_logs_left_behind(self):
        """Ensure gitignored log artifacts are not left by tests."""
        self.assertFalse((ROOT / "bot_logs.csv").exists())
        self.assertFalse((ROOT / "bot_metrics.csv").exists())


if __name__ == "__main__":
    unittest.main()
