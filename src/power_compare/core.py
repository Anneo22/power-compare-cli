"""Raw second-aligned power diagnostics. No calibration or fitted clock correction."""
from __future__ import annotations

import csv
import hashlib
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
METHOD = ("UTC second intersection, raw samples, zeros retained and gaps preserved. "
          "Explicit user offsets only; fitted lag never changes headline metrics. "
          "Positive differences mean the comparison reads higher.")


@dataclass
class Ride:
    name: str
    records: dict[datetime, dict[str, float | None]]
    sha256: str
    devices: list[dict]
    warnings: list[str]
    available_power_fields: list[str]
    selected_power_field: str


def _clock(value, *, fit=False):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            try:
                parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError("Timestamp must be ISO 8601 with timezone or Unix seconds") from error
        else:
            if not math.isfinite(number):
                raise ValueError("Timestamp must be finite")
            try:
                parsed = datetime.fromtimestamp(number, UTC)
            except (ValueError, OverflowError, OSError) as error:
                raise ValueError("Timestamp is outside the supported date range") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if not fit:
            raise ValueError("ISO timestamp requires an explicit timezone")
        parsed = parsed.replace(tzinfo=UTC)  # FIT timestamps are defined as UTC.
    return parsed.astimezone(UTC)


def _number(value, name):
    if value is None or str(value).strip().lower() in ("", "null", "none", "na", "n/a"):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{name} must be numeric or blank") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return number


def _rmse(differences):
    scale = max(map(abs, differences))
    return scale * math.sqrt(statistics.mean((d/scale)**2 for d in differences)) if scale else 0.0


def read_ride(path: Path, start: datetime | str | float | None = None, power_field: str = "power") -> Ride:
    """Read FIT or CSV; elapsed CSV requires the recording's actual UTC start.

    Fractional timestamps are floored to their UTC second. Duplicate seconds keep
    the last row and produce a warning. Device serials and positions are omitted.
    """
    path = Path(path)
    if path.suffix.lower() not in (".fit", ".csv"):
        raise ValueError("Supported inputs are .fit and .csv")
    records, devices, warnings, available = {}, [], [], set()
    duplicates = fractional = untimed = 0

    def add(timestamp, power, cadence, *, fit=False):
        nonlocal duplicates, fractional
        original = _clock(timestamp, fit=fit)
        timestamp = original.replace(microsecond=0)
        fractional += bool(original.microsecond)
        duplicates += timestamp in records
        records[timestamp] = {"power": _number(power, "Power"), "cadence": _number(cadence, "Cadence")}

    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            headers = [h.strip().lower() for h in (reader.fieldnames or [])]
            if len(headers) != len(set(headers)):
                raise ValueError("CSV contains duplicate column names")
            reader.fieldnames = headers
            clocks = [h for h in headers if h in ("timestamp", "datetime", "time", "elapsed_seconds", "seconds")]
            available.update(h for h in headers if "power" in h)
            selected = "power_w" if power_field == "power" and "power" not in headers and "power_w" in headers else power_field
            powers = [selected] if selected in headers else []
            cadences = [h for h in headers if h in ("cadence", "cadence_rpm")]
            if len(clocks) != 1 or len(powers) != 1 or len(cadences) > 1:
                raise ValueError("CSV needs one timestamp or elapsed_seconds column, one power column and optional cadence")
            elapsed = clocks[0] in ("elapsed_seconds", "seconds")
            if elapsed and start is None:
                raise ValueError("Elapsed CSV requires an explicit recording start; use --start LABEL=ISO")
            origin = _clock(start) if elapsed else None
            try:
                for line, row in enumerate(reader, 2):
                    try:
                        if None in row or any(value is None for value in row.values()):
                            raise ValueError("CSV row has the wrong number of columns")
                        raw_time = row[clocks[0]]
                        if elapsed:
                            seconds = _number(raw_time, "Elapsed seconds")
                            if seconds is None:
                                raise ValueError("Elapsed seconds cannot be blank")
                            timestamp = origin + timedelta(seconds=seconds)
                        else:
                            timestamp = raw_time
                        add(timestamp, row[powers[0]], row[cadences[0]] if cadences else None)
                    except (ValueError, OverflowError) as error:
                        raise ValueError(f"CSV row {line}: {error}") from error
            except csv.Error as error:
                raise ValueError("Malformed CSV: invalid quoting or oversized field") from error
    else:
        import fitdecode
        try:
            with fitdecode.FitReader(path, check_crc=fitdecode.CrcCheck.RAISE) as reader:
                for message in reader:
                    if not isinstance(message, fitdecode.FitDataMessage):
                        continue
                    values = {}
                    for field in message.fields:
                        definition = field.field_def
                        label = (f"developer:{definition.dev_data_index}:{field.name}" if definition and definition.is_dev else field.name)
                        values[label] = field.value
                        if message.name == "record" and (label == "power" or (str(field.units).lower() in ("w", "watt", "watts") and "power" in field.name.lower())):
                            if field.value is None or isinstance(field.value, (int, float)):
                                available.add(label)
                    if message.name == "record":
                        if values.get("timestamp") is None:
                            untimed += 1
                        else:
                            add(values["timestamp"], values.get(power_field), values.get("cadence"), fit=True)
                    elif message.name == "device_info":
                        device = {key: values[key] for key in ("manufacturer", "product_name", "source_type", "ant_device_type", "device_type", "ble_device_type")
                                  if isinstance(values.get(key), (str, int, float))}
                        if device and device not in devices:
                            devices.append(device)
        except fitdecode.FitError as error:
            raise ValueError(f"Invalid FIT file: {type(error).__name__}") from error
    if (power_field if path.suffix.lower() == ".fit" else selected) not in available:
        choices = ", ".join(sorted(available)) or "none"
        raise ValueError(f"Power field unavailable. Available power fields: {choices}")
    if not records:
        raise ValueError("Input has no timestamped records")
    if not any(row["power"] is not None for row in records.values()):
        raise ValueError("Input has no power samples")
    if duplicates:
        warnings.append(f"{duplicates} duplicate timestamp seconds; last record retained. Inspect before relying on results.")
    if fractional:
        warnings.append(f"{fractional} fractional timestamps floored to UTC seconds; no interpolation or averaging.")
    if untimed:
        warnings.append(f"{untimed} FIT records without timestamps excluded.")
    return Ride(path.name, dict(sorted(records.items())), hashlib.sha256(path.read_bytes()).hexdigest(), devices, warnings,
                sorted(available), power_field if path.suffix.lower() == ".fit" else selected)


def _metrics(reference, other, low=0, high=None, shift=0):
    start = min(reference)
    timed_rows = [(t, a, other[t + timedelta(seconds=shift)]) for t, a in reference.items()
            if low <= (t-start).total_seconds() and (high is None or (t-start).total_seconds() < high)
            and t + timedelta(seconds=shift) in other]
    rows = [(a, b) for _, a, b in timed_rows]
    valid_times = sorted(t for t, a, b in timed_rows if a.get("power") is not None and b.get("power") is not None)
    valid = [(a["power"], b["power"]) for a, b in rows if a.get("power") is not None and b.get("power") is not None]
    total = sum(a.get("power") is not None and low <= (t-start).total_seconds()
                and (high is None or (t-start).total_seconds() < high) for t, a in reference.items())
    end = high if high is not None else (max(reference)-start).total_seconds()+1
    expected = max(0, math.ceil(end)-math.ceil(low))
    run = longest = 0
    previous = None
    for timestamp in valid_times:
        run = run+1 if previous is not None and timestamp-previous == timedelta(seconds=1) else 1
        longest = max(longest, run)
        previous = timestamp
    result = {"samples": len(valid), "reference_window_samples": total,
              "coverage_percent": 100 * len(valid)/total if total else None,
              "window_expected_seconds": expected,
              "reference_time_coverage_percent": 100*total/expected if expected else None,
              "paired_time_coverage_percent": 100*len(valid)/expected if expected else None,
              "longest_paired_run_seconds": longest,
              "missing_power_at_common_timestamps": len(rows)-len(valid),
              "reference_zero_other_positive": sum(a == 0 and b > 50 for a, b in valid),
              "other_zero_reference_positive": sum(b == 0 and a > 50 for a, b in valid)}
    fields = ("reference_w", "comparison_w", "difference_w", "difference_percent", "mae_w", "rmse_w", "reference_sd_w", "comparison_sd_w")
    if not valid:
        return dict(result, **dict.fromkeys(fields))
    a, b = zip(*valid)
    differences = [y-x for x, y in valid]
    am, bm = statistics.mean(a), statistics.mean(b)
    result.update(reference_w=am, comparison_w=bm, difference_w=bm-am,
                  difference_percent=100*((bm-am)/am) if am else None,
                  mae_w=statistics.mean(abs(d) for d in differences),
                  rmse_w=_rmse(differences),
                  reference_sd_w=statistics.pstdev(a), comparison_sd_w=statistics.pstdev(b))
    return result


def compare(reference, other, low=0, high=None, shift=0):
    """Low-level raw comparison, retaining the prototype's no-overlap error."""
    result = _metrics(reference, other, low, high, shift)
    if result["samples"] == 0:
        raise ValueError("No overlapping non-missing power samples in selected window")
    return result


def _stage(metrics):
    if (metrics["samples"] < 30 or (metrics["coverage_percent"] or 0) < 80
            or (metrics["paired_time_coverage_percent"] or 0) < 80
            or metrics["longest_paired_run_seconds"] < 30):
        return "insufficient"
    if all(metrics[key + "_sd_w"] <= max(10, 0.10 * metrics[key + "_w"]) for key in ("reference", "comparison")):
        return "steady"
    return "variable"


def _lag(reference, other):
    # Identical support for every candidate prevents short-overlap overfitting.
    shifts = range(-10, 11)
    anchors = [t for t, a in reference.items() if a["power"] is not None
               and reference.get(t-timedelta(seconds=1), {}).get("power") is not None and all(
                   other.get(t+timedelta(seconds=s), {}).get("power") is not None
                   and other.get(t+timedelta(seconds=s-1), {}).get("power") is not None for s in shifts)]
    result = {"status": "insufficient", "shared_samples": len(anchors), "best_comparison_later_seconds": None, "scores": [],
              "method": "Centered, normalized one-second power changes on shared contiguous support; constant bias and linear ramps cannot identify lag. Raw RMSE is reported separately, never used to fit headline power."}
    if len(anchors) < 30:
        return result
    values = [reference[t]["power"] for t in anchors]
    changes = [reference[t]["power"]-reference[t-timedelta(seconds=1)]["power"] for t in anchors]
    change_sd = statistics.pstdev(changes)
    if (statistics.pstdev(values) < 5 or max(values)-min(values) < 20
            or change_sd < 1 or max(changes)-min(changes) < 5):
        result["status"] = "unidentifiable"
        return result
    scores = []
    change_mean = statistics.mean(changes)
    shape = [(value-change_mean)/change_sd for value in changes]
    for shift in shifts:
        differences = [other[t + timedelta(seconds=shift)]["power"]-reference[t]["power"] for t in anchors]
        other_changes = [other[t+timedelta(seconds=shift)]["power"]-other[t+timedelta(seconds=shift-1)]["power"] for t in anchors]
        other_sd = statistics.pstdev(other_changes)
        other_mean = statistics.mean(other_changes)
        shape_rmse = _rmse([(value-other_mean)/other_sd-ref for value, ref in zip(other_changes, shape)]) if other_sd else None
        scores.append({"comparison_later_seconds": shift, "samples": len(anchors),
                       "rmse_w": _rmse(differences), "shape_rmse": shape_rmse})
    candidates = [row for row in scores if row["shape_rmse"] is not None]
    if not candidates:
        result.update(status="unidentifiable", scores=scores)
        return result
    best = min(candidates, key=lambda row: (row["shape_rmse"], abs(row["comparison_later_seconds"])))
    tied = best["shape_rmse"] >= 1 or sum(math.isclose(row["shape_rmse"], best["shape_rmse"], abs_tol=0.01) for row in candidates) > 1
    result.update(status="unidentifiable" if tied else "diagnostic", scores=scores,
                  best_comparison_later_seconds=None if tied else best["comparison_later_seconds"])
    return result


def recommend_protocol(issue="mismatch", controller="computer", meters=()):
    """Reproducible next test, not an absolute calibration verdict."""
    if issue not in ("mismatch", "dropouts", "lag", "control"):
        raise ValueError("Issue must be mismatch, dropouts, lag or control")
    if controller not in ("computer", "watch", "phone", "none"):
        raise ValueError("Controller must be computer, watch, phone or none")
    steps = [
        "Warm up easily for 10 minutes so the trainer and meters reach operating temperature.",
        "Follow each meter manufacturer's current zero-offset/calibration procedure. Record the outcome, firmware and crank length where applicable; do not invent a correction factor.",
        f"Use only the {controller} to control trainer resistance." if controller != "none" else "Disable trainer control on every receiver and ride in a fixed resistance mode.",
        "Disable power matching. Record each meter separately and simultaneously; write down which sensor and ANT+ or Bluetooth link each receiver records.",
        "Start all recordings before pedalling and record 60 seconds at zero power, then 3 minutes each at easy, moderate and comfortably hard power with steady cadence. Mark exact stage times.",
        "Add three short controlled power changes, then 60 seconds coasting. Keep each receiver recording through the rests.",
        "Export original FIT files. Compare the last 2 minutes of each steady stage separately from transitions; inspect raw cadence, gaps and zeros.",
    ]
    if issue == "dropouts":
        steps.append("Repeat with receivers and ANT+/Bluetooth links swapped while leaving meters and workload unchanged. A fault following a receiver or link narrows the cause; an unmatched zero alone does not identify it.")
    elif issue == "lag":
        steps.append("Use the controlled changes to inspect lag. Change clocks only with independent timing evidence; do not apply the fitted lag to force agreement.")
    elif issue == "control":
        steps.append("Repeat the same stages with all trainer controllers disconnected, then reconnect one controller. Record when resistance changes independently of your command.")
    else:
        steps.append("If a repeatable difference persists, swap receiver/link assignments and repeat the same stages. Check manufacturer accuracy specifications at the measured power, drivetrain placement and any single-sided estimate.")
    return {"issue": issue, "controller": controller, "meters": list(meters), "steps": steps,
            "limits": ["Agreement between meters cannot establish absolute accuracy or validate FTP.",
                       "Keep original files unchanged. Resolve sensor/control evidence before changing training thresholds."]}


def compare_files(paths: list[Path], windows=(), offsets=None, *, starts=None, power_fields=None) -> dict:
    """Compare 2-6 sources against the first, with explicit source clock offsets.

    Offsets add seconds to source timestamps. Window ends are exclusive and are
    measured from the shifted reference start. Duplicate filenames gain ' (2)'.
    """
    if not 2 <= len(paths) <= 6:
        raise ValueError("Provide two to six input files")
    checked_windows = []
    for window in windows:
        if len(window) != 2 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in window) or window[0] < 0 or window[1] <= window[0]:
            raise ValueError("Windows require finite 0 <= START < END")
        checked_windows.append(tuple(window))
    offsets, starts, power_fields = offsets or {}, starts or {}, power_fields or {}
    names, counts = [], {}
    for path in paths:
        base = Path(path).name
        counts[base] = counts.get(base, 0) + 1
        names.append(base if counts[base] == 1 else f"{base} ({counts[base]})")
    for mapping in (offsets, starts, power_fields):
        if set(mapping)-set(names):
            raise ValueError("Clock labels must match source filenames (including duplicate suffixes)")
    for value in offsets.values():
        if not isinstance(value, (float, int)) or not math.isfinite(value) or int(value) != value:
            raise ValueError("Clock offsets must be finite whole seconds")
    rides = []
    for path, name in zip(paths, names):
        ride = read_ride(path, starts.get(name), power_fields.get(name, "power"))
        ride.name = name
        offset = offsets.get(name, 0)
        if offset:
            try:
                ride.records = {t + timedelta(seconds=offset): row for t, row in ride.records.items()}
            except OverflowError as error:
                raise ValueError("Clock offset is outside the supported date range") from error
            ride.warnings.append(f"Explicit user clock offset: {offset:+g} seconds added to timestamps.")
        rides.append(ride)
    reference = rides[0].records
    origin = min(reference)
    sources = [{"name": ride.name, "sha256": ride.sha256,
                "start": (min(ride.records)-timedelta(seconds=offsets.get(ride.name, 0))).isoformat(),
                "end": (max(ride.records)-timedelta(seconds=offsets.get(ride.name, 0))).isoformat(),
                "records": len(ride.records), "devices": ride.devices,
                "warnings": ride.warnings, "offset_seconds": offsets.get(ride.name, 0),
                "available_power_fields": ride.available_power_fields, "selected_power_field": ride.selected_power_field,
                "plot": [[(t-origin).total_seconds(), row["power"], row["cadence"]] for t, row in ride.records.items()]}
               for ride in rides]
    comparisons = []
    for ride in rides[1:]:
        whole = _metrics(reference, ride.records)
        alerts = ["Agreement cannot establish absolute accuracy or validate FTP. No source samples are corrected."]
        if whole["samples"] < 30:
            alerts.append("Insufficient shared power samples: at least 30 are required for stage interpretation.")
        if (whole["coverage_percent"] or 0) < 95:
            alerts.append("Incomplete overlap: check unequal starts, pauses, timestamps and missing records.")
        if (whole["reference_time_coverage_percent"] or 0) < 95:
            alerts.append("Sparse or missing reference power: paired/reference coverage alone does not describe support across elapsed time.")
        if whole["reference_zero_other_positive"] or whole["other_zero_reference_positive"]:
            alerts.append("Unmatched zero-power samples: inspect cadence and raw traces; these do not automatically diagnose sensor dropouts.")
        stage_rows = []
        for low, high in checked_windows:
            metrics = _metrics(reference, ride.records, low, high)
            stage = _stage(metrics)
            stage_rows.append(dict(seconds=[low, high], stage=stage, **metrics))
            if stage != "steady":
                alerts.append(f"Window {low:g}:{high:g} is {stage}; do not interpret its mean as steady-stage agreement.")
        if not checked_windows:
            alerts.append("Select known steady-stage windows. Whole-ride averages mix steady riding, surges and coasting.")
        alerts.extend(w for r in (rides[0], ride) for w in r.warnings if "duplicate" in w)
        comparisons.append({"name": ride.name, "whole": whole, "windows": stage_rows,
                            "lag": _lag(reference, ride.records), "alerts": alerts})
    return {"reference": rides[0].name, "method": METHOD, "sources": sources, "comparisons": comparisons,
            "guidance": ["Check source labels, clock offsets and coverage before interpreting a power difference.",
                         "Steady means and transition/lag diagnostics answer different questions; compare repeated steady stages before changing a training threshold.",
                         "Steady labels are screening heuristics: at least 30 contiguous paired seconds, 80% paired/reference and elapsed-window coverage, and SD no greater than max(10 W, 10% of mean) on both sources."],
            "protocol": recommend_protocol()["steps"]}
