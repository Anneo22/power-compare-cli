import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from power_compare.cli import main


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.a = self.directory / "a.csv"
        self.b = self.directory / "b.csv"
        self.a.write_text("timestamp,power\n2026-01-01T00:00:00Z,100\n")
        self.b.write_text("timestamp,power\n2026-01-01T00:00:00Z,110\n")

    def run_cli(self, args, error=False):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            if error:
                with self.assertRaises(SystemExit) as caught:
                    main(args)
                self.assertEqual(caught.exception.code, 2)
            else:
                self.assertEqual(main(args), 0)
        return stdout.getvalue(), stderr.getvalue()

    def test_json_stdout_without_report(self):
        stdout, _ = self.run_cli(["compare", str(self.a), str(self.b)])
        self.assertEqual(json.loads(stdout)["comparisons"][0]["whole"]["difference_w"], 10)
        self.assertNotIn(str(self.directory), stdout)

    def test_protocol_json(self):
        stdout, _ = self.run_cli(["protocol", "--issue", "lag", "--controller", "watch"])
        self.assertEqual(json.loads(stdout)["issue"], "lag")

    def test_windows_and_offsets_validation(self):
        for extra in (["--window", "nan:10"], ["--window", "10:0"], ["--window", "0:1:2"], ["--offset", "a.csv=nan"], ["--offset", "unknown=1"], ["--offset", "a.csv=1", "--offset", "a.csv=2"]):
            with self.subTest(extra=extra):
                self.run_cli(["compare", str(self.a), str(self.b), *extra], error=True)

    def test_output_overwrite_and_input_collision_rejected(self):
        prefix = self.directory / "report"
        Path(str(prefix)+".html").write_text("keep me")
        self.run_cli(["compare", str(self.a), str(self.b), "--out", str(prefix)], error=True)
        self.assertEqual(Path(str(prefix)+".html").read_text(), "keep me")
        collision = self.directory / "report.json"
        collision.write_text("keep input")
        self.run_cli(["compare", str(collision), str(self.b), "--out", str(prefix)], error=True)
        self.assertEqual(collision.read_text(), "keep input")

    def test_report_files_are_exclusive(self):
        prefix = self.directory / "report"
        with patch("power_compare.web.render_report", return_value="<!doctype html><title>Report</title>"):
            self.run_cli(["compare", str(self.a), str(self.b), "--out", str(prefix)])
        saved = Path(str(prefix)+".json").read_text()
        self.assertEqual(json.loads(saved)["reference"], "a.csv")
        self.run_cli(["compare", str(self.a), str(self.b), "--out", str(prefix)], error=True)
        self.assertEqual(Path(str(prefix)+".json").read_text(), saved)

    def test_elapsed_start_in_cli(self):
        self.a.write_text("elapsed_seconds,power\n0,100\n")
        stdout, _ = self.run_cli(["compare", str(self.a), str(self.b), "--start", "a.csv=2026-01-01T00:00:00Z"])
        self.assertEqual(json.loads(stdout)["comparisons"][0]["whole"]["samples"], 1)

    def test_same_file_explicit_channel_selection(self):
        self.a.write_text("timestamp,power,other_power\n2026-01-01T00:00:00Z,100,120\n")
        stdout, _ = self.run_cli(["compare", str(self.a), str(self.a), "--power-field", "a.csv (2)=other_power"])
        self.assertEqual(json.loads(stdout)["comparisons"][0]["whole"]["difference_w"], 20)

    def test_report_uses_actual_html_renderer(self):
        prefix = self.directory / "real-report"
        self.run_cli(["compare", str(self.a), str(self.b), "--out", str(prefix)])
        html = Path(str(prefix)+".html").read_text()
        self.assertIn("Power", html)
        self.assertIn("a.csv", html)
        self.assertNotIn("https://", html)


if __name__ == "__main__":
    unittest.main()
