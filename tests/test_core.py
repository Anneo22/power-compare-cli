import json
import math
import struct
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from power_compare.core import compare, compare_files, read_ride, recommend_protocol


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def csv(self, name, powers, seconds=None, shift=0, header="timestamp,power,cadence"):
        path = self.directory / name
        seconds = list(range(len(powers))) if seconds is None else seconds
        rows = [header]
        for second, power in zip(seconds, powers):
            clock = (self.start + timedelta(seconds=second+shift)).isoformat()
            if header.startswith("elapsed_seconds"):
                clock = str(second)
            rows.append(f"{clock},{'' if power is None else power},90")
        path.write_text("\n".join(rows), encoding="utf-8")
        return path

    def test_identity_and_known_bias(self):
        a = self.csv("a.csv", [100]*60)
        b = self.csv("b.csv", [110]*60)
        result = compare_files([a, b], [(0, 60)])
        metrics = result["comparisons"][0]["whole"]
        self.assertEqual(metrics["difference_w"], 10)
        self.assertEqual(metrics["difference_percent"], 10)
        self.assertEqual(metrics["rmse_w"], 10)
        self.assertEqual(result["comparisons"][0]["windows"][0]["stage"], "steady")
        self.assertEqual(compare_files([a, a])["comparisons"][0]["whole"]["rmse_w"], 0)
        self.assertEqual(result["comparisons"][0]["lag"]["status"], "unidentifiable")

    def test_gaps_missing_and_zeros_preserved(self):
        a = self.csv("a.csv", [100]*10)
        b = self.csv("b.csv", [0, None]+[100]*6, [0, 1, 2, 3, 6, 7, 8, 9])
        result = compare_files([a, b])
        metrics = result["comparisons"][0]["whole"]
        self.assertEqual(metrics["samples"], 7)
        self.assertEqual(metrics["coverage_percent"], 70)
        self.assertEqual(metrics["missing_power_at_common_timestamps"], 1)
        self.assertEqual(metrics["other_zero_reference_positive"], 1)
        self.assertEqual(result["sources"][1]["plot"][4][0], 6)
        self.assertIn("do not automatically diagnose", " ".join(result["comparisons"][0]["alerts"]))

    def test_no_overlap_returns_null_metrics_and_alert(self):
        a = self.csv("a.csv", [100]*10)
        b = self.csv("b.csv", [100]*10, shift=100)
        result = compare_files([a, b])
        self.assertEqual(result["comparisons"][0]["whole"]["samples"], 0)
        self.assertIsNone(result["comparisons"][0]["whole"]["rmse_w"])
        with self.assertRaises(ValueError):
            compare(read_ride(a).records, read_ride(b).records)
        json.dumps(result, allow_nan=False)

    def test_explicit_offsets_separate_from_lag(self):
        powers = [100+(i*37 % 200) for i in range(100)]
        a = self.csv("a.csv", powers)
        b = self.csv("b.csv", powers, shift=2)
        result = compare_files([a, b])
        self.assertEqual(result["comparisons"][0]["lag"]["best_comparison_later_seconds"], 2)
        self.assertGreater(result["comparisons"][0]["whole"]["rmse_w"], 0)
        corrected = compare_files([a, b], offsets={"b.csv": -2})
        self.assertEqual(corrected["comparisons"][0]["whole"]["rmse_w"], 0)
        self.assertEqual(corrected["sources"][1]["offset_seconds"], -2)
        self.assertEqual(read_ride(b).records[min(read_ride(b).records)]["power"], powers[0])

    def test_lag_does_not_overfit_short_recording(self):
        a = self.csv("a.csv", [100+i for i in range(10)])
        b = self.csv("b.csv", [100+i for i in range(10)], shift=2)
        lag = compare_files([a, b])["comparisons"][0]["lag"]
        self.assertEqual(lag["status"], "insufficient")
        self.assertEqual(lag["scores"], [])

    def test_constant_bias_on_linear_ramp_cannot_identify_lag(self):
        a = self.csv("a.csv", [100+i for i in range(100)])
        b = self.csv("b.csv", [110+i for i in range(100)])
        result = compare_files([a, b])
        self.assertEqual(result["comparisons"][0]["whole"]["difference_w"], 10)
        self.assertEqual(result["comparisons"][0]["lag"]["status"], "unidentifiable")
        self.assertIsNone(result["comparisons"][0]["lag"]["best_comparison_later_seconds"])

    def test_transition_lag_survives_constant_bias_and_gain(self):
        powers = [100+(i*37 % 200) for i in range(120)]
        a = self.csv("a.csv", powers)
        b = self.csv("b.csv", [value*1.1+40 for value in powers], shift=3)
        result = compare_files([a, b])
        self.assertEqual(result["comparisons"][0]["lag"]["best_comparison_later_seconds"], 3)
        self.assertGreater(result["comparisons"][0]["whole"]["rmse_w"], 40)

    def test_window_with_mostly_null_reference_is_insufficient(self):
        a = self.csv("a.csv", [100]*30+[None]*570)
        result = compare_files([a, a], [(0, 600)])
        metrics = result["comparisons"][0]["windows"][0]
        self.assertEqual(metrics["coverage_percent"], 100)
        self.assertEqual(metrics["reference_time_coverage_percent"], 5)
        self.assertEqual(metrics["paired_time_coverage_percent"], 5)
        self.assertEqual(metrics["stage"], "insufficient")

    def test_sparse_window_is_insufficient_despite_complete_pair_coverage(self):
        a = self.csv("a.csv", [100]*30, seconds=list(range(0, 600, 20)))
        metrics = compare_files([a, a], [(0, 600)])["comparisons"][0]["windows"][0]
        self.assertEqual(metrics["coverage_percent"], 100)
        self.assertEqual(metrics["paired_time_coverage_percent"], 5)
        self.assertEqual(metrics["longest_paired_run_seconds"], 1)
        self.assertEqual(metrics["stage"], "insufficient")

    def test_window_exclusive_end_and_variable_stage(self):
        a = self.csv("a.csv", [0, 400]*30)
        result = compare_files([a, a], [(2, 5), (0, 60)])
        windows = result["comparisons"][0]["windows"]
        self.assertEqual(windows[0]["samples"], 3)
        self.assertEqual(windows[0]["reference_w"], 400/3)
        self.assertEqual(windows[1]["stage"], "variable")

    def test_elapsed_requires_start_and_timezone(self):
        a = self.csv("a.csv", [100]*3, header="elapsed_seconds,power,cadence")
        with self.assertRaisesRegex(ValueError, "explicit recording start"):
            read_ride(a)
        with self.assertRaisesRegex(ValueError, "explicit timezone"):
            read_ride(a, "2026-01-01T00:00:00")
        ride = read_ride(a, "2026-01-01T01:00:00+01:00")
        self.assertEqual(min(ride.records), self.start)
        self.assertEqual(compare_files([a, a], starts={"a.csv": self.start, "a.csv (2)": self.start})["comparisons"][0]["whole"]["rmse_w"], 0)

    def test_unix_and_fractional_timestamps_duplicates(self):
        path = self.directory / "a.csv"
        path.write_text("timestamp,power\n1767225600.1,100\n1767225600.9,120\n1767225601,0\n")
        ride = read_ride(path)
        self.assertEqual(min(ride.records), self.start)
        self.assertEqual(ride.records[self.start]["power"], 120)
        self.assertEqual(len(ride.warnings), 2)

    def test_input_validation(self):
        path = self.directory / "bad.csv"
        for body in ("timestamp,power\n2026-01-01T00:00:00Z,nan\n", "timestamp,power\n2026-01-01T00:00:00Z,-1\n", "timestamp,power\n2026-01-01T00:00:00Z,\n", "timestamp,power\n2026-01-01T00:00:00Z,100,90\n", "timestamp,power,power\n2026-01-01T00:00:00Z,100,100\n", "timestamp,power\n,100\n"):
            with self.subTest(body=body):
                path.write_text(body)
                with self.assertRaises(ValueError):
                    read_ride(path)
        path = self.csv("a.csv", [100])
        for windows in ([(1, 0)], [(0, math.inf)], [(0, 1, 2)]):
            with self.assertRaises(ValueError):
                compare_files([path, path], windows)
        for offsets in ({"unknown": 1}, {"a.csv": math.nan}, {"a.csv": 0.1}):
            with self.assertRaises(ValueError):
                compare_files([path, path], offsets=offsets)
        with self.assertRaises(ValueError):
            compare_files([path]*7)

    def test_malformed_csv_is_a_user_error(self):
        path = self.directory / "bad.csv"
        path.write_text('timestamp,power\n"unclosed,100\n')
        with self.assertRaisesRegex(ValueError, "Malformed CSV"):
            read_ride(path)

    def test_zero_percentage_is_undefined(self):
        a = self.csv("a.csv", [0]*10)
        self.assertIsNone(compare_files([a, a])["comparisons"][0]["whole"]["difference_percent"])

    def test_invalid_fit_is_rejected(self):
        path = self.directory / "a.fit"
        path.write_bytes(b"invalid fit")
        with self.assertRaises(ValueError):
            read_ride(path)

    def test_real_fit_native_developer_channels_crc_and_privacy(self):
        # Small synthetic binary FIT: device info, developer description, records.
        from fitdecode.utils import compute_crc

        def definition(local, global_id, fields, developer=None):
            result = bytes([0x40 | local | (0x20 if developer else 0), 0, 0])
            result += struct.pack("<HB", global_id, len(fields))
            result += b"".join(bytes(field) for field in fields)
            if developer:
                result += bytes([len(developer)]) + b"".join(bytes(field) for field in developer)
            return result

        data = definition(0, 207, [(3, 1, 2)]) + b"\x00\x00"
        data += definition(1, 206, [(0, 1, 2), (1, 1, 2), (2, 1, 2), (3, 12, 7), (8, 6, 7)])
        data += b"\x01\x00\x00\x84" + b"Other Power\x00" + b"watts\x00"
        data += definition(2, 23, [(2, 2, 0x84), (3, 4, 0x86)])
        data += b"\x02" + struct.pack("<HI", 1, 123456789)
        data += definition(3, 20, [(253, 4, 0x86), (7, 2, 0x84), (4, 1, 2)], [(0, 2, 0)])
        epoch = datetime(1989, 12, 31, tzinfo=timezone.utc)
        timestamp = int((self.start-epoch).total_seconds())
        for index in range(60):
            data += b"\x03" + struct.pack("<IHBH", timestamp+index, 100, 90, 110)
        header = struct.pack("<BBHI4s", 14, 0x10, 100, len(data), b".FIT")
        header += struct.pack("<H", compute_crc(header))
        payload = header + data
        path = self.directory / "channels.fit"
        path.write_bytes(payload + struct.pack("<H", compute_crc(payload)))
        native = read_ride(path)
        self.assertEqual(native.available_power_fields, ["developer:0:Other Power", "power"])
        self.assertEqual(native.records[self.start]["power"], 100)
        self.assertEqual(native.devices, [{"manufacturer": "garmin"}])
        result = compare_files([path, path], power_fields={"channels.fit (2)": "developer:0:Other Power"})
        self.assertEqual(result["comparisons"][0]["whole"]["difference_w"], 10)
        self.assertNotIn("serial_number", json.dumps(result))
        self.assertNotIn("123456789", json.dumps(result))
        path.write_bytes(path.read_bytes()[:-2] + b"\x00\x00")
        with self.assertRaisesRegex(ValueError, "Invalid FIT"):
            read_ride(path)

    def test_csv_explicit_power_channel(self):
        path = self.directory / "channels.csv"
        path.write_text("timestamp,power,other_power\n2026-01-01T00:00:00Z,100,120\n")
        result = compare_files([path, path], power_fields={"channels.csv (2)": "other_power"})
        self.assertEqual(result["comparisons"][0]["whole"]["difference_w"], 20)
        with self.assertRaisesRegex(ValueError, "CSV needs"):
            read_ride(path, power_field="missing_power")

    def test_protocol_limits_and_control(self):
        protocol = recommend_protocol("dropouts", "none", ["Trainer", "Crank"])
        self.assertIn("Disable trainer control", protocol["steps"][2])
        self.assertIn("swapped", protocol["steps"][-1])
        self.assertIn("absolute accuracy", protocol["limits"][0])
        with self.assertRaises(ValueError):
            recommend_protocol("magic")


if __name__ == "__main__":
    unittest.main()
