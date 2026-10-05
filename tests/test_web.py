import csv
import io
import re
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from power_compare.core import compare_files
from power_compare.web import STYLE, make_server, render_report


def recording(power=100, *, elapsed=False):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["elapsed_seconds" if elapsed else "timestamp", "power", "cadence"])
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for second in range(60):
        writer.writerow([second if elapsed else (start + timedelta(seconds=second)).isoformat(), power, 90])
    return buffer.getvalue().encode()


class WebTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.port = self.server.server_address[1]
        self.host = f"127.0.0.1:{self.port}"
        status, page, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.token = re.search(r'name="token" value="([^"]+)"', page).group(1)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read().decode(), dict(response.getheaders())
        finally:
            connection.close()

    def form(self, files=None, fields=None):
        boundary = "power-compare-test-boundary"
        body = bytearray()
        entries = {"token": self.token, **(fields or {})}
        for name, value in entries.items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        for filename, payload in files if files is not None else [("reference.csv", recording()), ("meter.csv", recording(110))]:
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
            body.extend(payload)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        return bytes(body), {"Content-Type": f"multipart/form-data; boundary={boundary}", "Origin": f"http://{self.host}"}

    def test_real_upload_analysis_report_and_temporary_cleanup(self):
        observed = []

        def inspect(paths, **kwargs):
            observed.extend(paths)
            return compare_files(paths, **kwargs)

        body, headers = self.form(fields={"windows": "0:60"})
        with patch("power_compare.core.compare_files", side_effect=inspect):
            status, report, response_headers = self.request("POST", "/compare", body, headers)
        self.assertEqual(status, 200)
        self.assertIn("100.0 W", report)
        self.assertIn("110.0 W", report)
        self.assertIn("10.0 W", report)
        self.assertIn("100.0%", report)
        self.assertIn("0–60 s · steady", report)
        self.assertIn("Minutes from reference start", report)
        self.assertIn("Power (W)", report)
        self.assertIn("SHA-256", report)
        self.assertIn("not establish absolute calibration", report)
        self.assertTrue(observed)
        self.assertTrue(all(not path.exists() for path in observed))
        self.assertNotIn(str(observed[0].parent), report)
        self.assertEqual(response_headers["Cache-Control"], "no-store")
        self.assertEqual(response_headers["Referrer-Policy"], "same-origin")
        self.assertNotIn("Access-Control-Allow-Origin", response_headers)

    def test_foreign_origin_host_and_csrf_rejected(self):
        body, headers = self.form()
        headers["Origin"] = "https://evil.example"
        self.assertEqual(self.request("POST", "/compare", body, headers)[0], 403)
        headers["Origin"] = "null"
        self.assertEqual(self.request("POST", "/compare", body, headers)[0], 403)
        self.assertEqual(self.request("GET", "/", headers={"Host": "evil.example"})[0], 403)
        body, headers = self.form(fields={"token": "wrong-token"})
        self.assertEqual(self.request("POST", "/compare", body, headers)[0], 403)
        body, headers = self.form(fields={"token": "non-ascii-☃"})
        self.assertEqual(self.request("POST", "/compare", body, headers)[0], 403)

    def test_case_distinct_filenames_keep_independent_recordings(self):
        results = []

        def capture(paths, **kwargs):
            self.assertNotEqual(paths[0].parent, paths[1].parent)
            result = compare_files(paths, **kwargs)
            results.append(result)
            return result

        body, headers = self.form(files=[("Meter.csv", recording(100)), ("meter.csv", recording(200))])
        with patch("power_compare.core.compare_files", side_effect=capture):
            status, page, _ = self.request("POST", "/compare", body, headers)
        self.assertEqual(status, 200)
        self.assertIn("100.0 W", page)
        self.assertIn("200.0 W", page)
        self.assertEqual(results[0]["comparisons"][0]["whole"]["difference_w"], 100)
        self.assertNotEqual(results[0]["sources"][0]["sha256"], results[0]["sources"][1]["sha256"])

    def test_size_rejected_before_read_or_analysis(self):
        with patch("power_compare.web.MAX_UPLOAD_BYTES", 50):
            body, headers = self.form()
            self.assertEqual(self.request("POST", "/compare", body, headers)[0], 413)

    def test_invalid_filenames_duplicate_files_formats_counts(self):
        cases = [
            [("../escape.csv", recording()), ("good.csv", recording())],
            [("folder\\escape.csv", recording()), ("good.csv", recording())],
            [("same.csv", recording()), ("same.csv", recording())],
            [("script.html", b"<script>"), ("good.csv", recording())],
            [("empty.fit", b""), ("good.csv", recording())],
            [(f"meter-{i}.csv", recording()) for i in range(7)],
            [("only.csv", recording())],
        ]
        for files in cases:
            with self.subTest(files=[name for name, _ in files]):
                body, headers = self.form(files=files)
                self.assertEqual(self.request("POST", "/compare", body, headers)[0], 400)

    def test_settings_validation_and_explicit_clocks(self):
        for fields in ({"windows": "20:10"}, {"windows": "nan:40"}, {"offsets": "unknown.csv=1"}, {"offsets": "meter.csv=inf"}):
            with self.subTest(fields=fields):
                body, headers = self.form(fields=fields)
                self.assertEqual(self.request("POST", "/compare", body, headers)[0], 400)
        body, headers = self.form(files=[("reference.csv", recording(elapsed=True)), ("meter.csv", recording(110, elapsed=True))], fields={"starts": "reference.csv=2026-01-01T00:00:00Z\nmeter.csv=2026-01-01T00:00:00Z", "offsets": "meter.csv=1"})
        status, page, _ = self.request("POST", "/compare", body, headers)
        self.assertEqual(status, 200)
        self.assertIn("1.0 s, explicit only", page)
        self.assertIn("98.3%", page)

    def test_sparse_stage_exposes_elapsed_time_coverage(self):
        body, headers = self.form(fields={"windows": "0:600"})
        status, page, _ = self.request("POST", "/compare", body, headers)
        self.assertEqual(status, 200)
        self.assertIn("0–600 s · insufficient", page)
        self.assertIn("Paired / ref", page)
        self.assertIn("Time coverage", page)
        self.assertIn("100.0%</td><td>10.0%", page)

    def test_protocol_selection_and_escaped_equipment(self):
        status, page, _ = self.request("GET", "/?issue=dropouts&controller=none&meters=%3Cscript%3E")
        self.assertEqual(status, 200)
        self.assertIn("receivers and ANT+/Bluetooth links swapped", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)
        self.assertIn('id="reference-file"', page)

    def test_palette_is_declared_on_a_valid_root_selector(self):
        # A stray leading combinator silently invalidates the palette rule.
        root = re.search(r"(?:^|\})\s*:root\s*\{([^}]+)\}", STYLE)
        self.assertIsNotNone(root, "The theme must use a valid standalone :root selector")
        declarations = dict(item.split(":", 1) for item in root.group(1).split(";") if ":" in item)
        self.assertEqual(declarations["--paper"], "#f7f6f0")
        self.assertEqual(declarations["--ink"], "#202c2c")
        self.assertEqual(declarations["--accent"], "#096b66")

    def test_control_conflict_and_phone_recipe_are_selectable(self):
        status, page, _ = self.request("GET", "/?issue=control&controller=phone")
        self.assertEqual(status, 200)
        self.assertIn('<option value="control" selected>Trainer control conflicts</option>', page)
        self.assertIn('<option value="phone" selected>Phone / training app</option>', page)
        self.assertIn("Use only the phone to control trainer resistance", page)
        self.assertIn("all trainer controllers disconnected", page)

    def test_report_escaping_null_metrics_and_trace_gaps(self):
        hostile = '<script>alert("x")</script>'
        result = {"reference": hostile, "method": hostile, "sources": [{"name": hostile, "start": hostile, "end": hostile, "sha256": hostile, "devices": [hostile], "warnings": [hostile], "plot": [[0, 100, 90], [1, None, None], [2, 0, 0], [8, 110, 90]]}], "comparisons": [{"name": hostile, "whole": {"samples": 0, "difference_w": None}, "alerts": [hostile], "lag": {"status": hostile}}], "guidance": [hostile], "protocol": [hostile]}
        page = render_report(result)
        self.assertNotIn("<script>", page)
        self.assertNotIn("alert(\"x\")", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("Unavailable", page)
        self.assertIn("Zeros remain visible", page)
        # Every valid sample is a move: null and the long gap break the raw trace.
        trace = re.search(r'<path d="([^"]+)" fill="none" stroke="#202c2c" stroke-width="1.6"', page).group(1)
        self.assertEqual(trace.count("M"), 3)
        self.assertNotIn("L", trace)

    def test_no_remote_bind_or_arbitrary_paths(self):
        for host in ("0.0.0.0", "192.0.2.1", "example.com"):
            with self.assertRaises(ValueError):
                make_server(host=host, port=0)
        self.assertEqual(self.request("GET", "/etc/passwd")[0], 404)


if __name__ == "__main__":
    unittest.main()
