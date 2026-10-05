"""A temporary, loopback-only workspace and portable comparison report."""

from __future__ import annotations

import html
import ipaddress
import math
import secrets
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_FILES = 6

STYLE = """:root{color-scheme:light;--paper:#f7f6f0;--ink:#202c2c;--muted:#556261;--rule:#c6ccc5;--accent:#096b66;--field:#fffefa}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
::selection{background:#b7d9d1;color:var(--ink)}a{color:var(--accent);text-underline-offset:.2em}a:hover{color:var(--ink)}
main{max-width:1120px;margin:0 auto;padding:36px 40px 64px}header{display:flex;align-items:center;justify-content:space-between;gap:24px;padding-bottom:24px;border-bottom:1px solid var(--rule)}
.brand{display:flex;align-items:center;gap:12px;font-size:19px;letter-spacing:-.025em;font-weight:650}.brand svg{width:48px;height:36px}.local{font-size:13px;color:var(--muted)}
h1,h2,h3{line-height:1.16;font-weight:400;text-wrap:balance}h1{font-family:Georgia,"Times New Roman",serif;font-size:clamp(32px,4.6vw,52px);letter-spacing:-.035em;max-width:760px;margin:42px 0 18px}
h2{font-size:24px;letter-spacing:-.025em;margin:0 0 18px}h3{font-size:18px;margin:24px 0 12px;font-weight:600}p{max-width:72ch;margin:0 0 18px}.intro{color:var(--muted);font-size:18px;max-width:65ch}
section{margin-top:42px;padding-top:32px;border-top:1px solid var(--rule)}.layout{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:64px;margin-top:42px}.layout section{margin:0;padding:0;border:0}
label{display:block;font-weight:600;margin:0 0 6px}.hint{display:block;font-weight:400;color:var(--muted);font-size:14px;margin:5px 0 12px}input,select,textarea,button{font:inherit;caret-color:var(--accent)}
input,select,textarea{width:100%;border:1px solid var(--rule);background:var(--field);color:var(--ink);border-radius:4px;padding:10px 12px;min-height:46px}input[type=file]{padding:16px 12px;border-style:dashed;font-size:14px}input[type=file]::file-selector-button{font:inherit;background:var(--paper);border:1px solid var(--rule);border-radius:3px;padding:6px 10px;margin-right:12px;color:var(--ink);cursor:pointer}
textarea{resize:vertical;min-height:96px}input::placeholder,textarea::placeholder{color:var(--muted);opacity:1}button{border:0;background:var(--accent);color:#fff;border-radius:4px;padding:12px 20px;cursor:pointer;font-weight:600;min-height:48px}button:hover{background:#075750}button:disabled{opacity:.6;cursor:wait}:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
.field{margin-bottom:22px}.row{display:grid;grid-template-columns:1fr 1fr;gap:16px}.secondary{background:transparent;color:var(--accent);border:1px solid var(--accent);padding:8px 14px;min-height:44px}.secondary:hover{background:#e8eee6;color:var(--ink)}details{margin:24px 0}summary{cursor:pointer;color:var(--accent);font-weight:600;min-height:36px}details[open]>summary{margin-bottom:16px}
ol,ul{padding-left:24px;margin:12px 0 22px}li{padding-left:4px;margin:10px 0}small,.muted{color:var(--muted)}.note{font-size:14px}.protocol{font-size:15px}.protocol li{margin-bottom:16px}.table-wrap{overflow-x:auto;scrollbar-color:var(--accent) var(--paper)}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:12px 14px 12px 0;border-bottom:1px solid var(--rule);vertical-align:top}th{font-weight:600;color:var(--muted);white-space:nowrap}td:not(:first-child){white-space:nowrap}caption{text-align:left;font-size:14px;color:var(--muted);padding:0 0 14px}.chart{width:100%;height:auto;display:block;margin:18px 0}
.legend{display:flex;flex-wrap:wrap;gap:12px 24px;list-style:none;padding:0;font-size:14px}.legend li{display:flex;align-items:center;gap:8px;margin:0;overflow-wrap:anywhere}.legend svg{flex:none}.axis{font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:var(--muted)}.hash{font:12px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere;max-width:60ch}
.sources{display:grid;grid-template-columns:1fr 1fr;gap:24px 48px}.source{min-width:0}.source h3{overflow-wrap:anywhere}.source dl{font-size:14px;margin:0}.source dt{color:var(--muted);float:left;clear:left;width:92px}.source dd{margin:0 0 6px 100px;overflow-wrap:anywhere}.alerts{border-top:1px solid var(--rule);padding-top:20px}.back{display:inline-block;margin-top:24px}.error{max-width:65ch}
footer{margin-top:52px;border-top:1px solid var(--rule);padding-top:20px;font-size:13px;color:var(--muted)}
@media(max-width:760px){main{padding:24px 22px 40px}header{align-items:flex-start}.local{max-width:120px;text-align:right}h1{margin-top:32px}.layout{grid-template-columns:1fr;gap:38px;margin-top:32px}.layout section+section{border-top:1px solid var(--rule);padding-top:30px}.sources{grid-template-columns:1fr}.row{grid-template-columns:1fr;gap:0}section{margin-top:32px;padding-top:26px}.chart{min-width:620px}.chart-scroll{overflow-x:auto;scrollbar-color:var(--accent) var(--paper)}button{width:100%}td,th{padding-right:18px}.legend{gap:12px 16px}}
@media print{body{background:white}main{padding:0;max-width:none}header .local,.back{display:none}section,.source{break-inside:avoid}.chart{min-width:0}a{color:inherit}}
"""

MARK = '<svg viewBox="0 0 64 48" fill="none" aria-hidden="true"><path d="M4 29h14V9h24v20h18" stroke="#202c2c" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/><path d="M4 40h14V20h24v20h18" stroke="#096b66" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/></svg>'


def _document(title: str, content: str, *, report: bool = False) -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_escape(title)} · Power Compare</title><style>{STYLE}</style></head><body><main><header><div class="brand">{MARK}<span>Power Compare</span></div><span class="local">{'Standalone comparison report' if report else 'Local workspace · no account'}</span></header>{content}<footer>Power Compare compares recordings. It does not establish absolute calibration. No remote services, analytics, or external assets.</footer></main></body></html>'''


def _error_page(message: str) -> str:
    return _document("Upload needs attention", f'<h1>Check the upload.</h1><p class="error" role="alert">{_escape(message)}</p><a class="back" href="/">Return to the workspace</a>')


def _protocol_lines(protocol: dict | list | tuple) -> list[str]:
    if isinstance(protocol, dict):
        for key in ("steps", "protocol", "recording_steps"):
            if key in protocol:
                return [str(item) for item in protocol[key]]
        return [str(value) for value in protocol.values() if isinstance(value, str)]
    return [str(item) for item in protocol]


def render_upload(token: str, protocol: dict, issue: str = "mismatch", controller: str = "computer", meters: str = "") -> str:
    """Render the native form, including a recipe before collecting recordings."""
    def options(values: tuple[tuple[str, str], ...], current: str) -> str:
        return "".join(f'<option value="{value}"{" selected" if current == value else ""}>{label}</option>' for value, label in values)

    steps = "".join(f"<li>{_escape(step)}</li>" for step in _protocol_lines(protocol))
    issue_options = options((("mismatch", "Power readings disagree"), ("dropouts", "Gaps or zero readings"), ("lag", "One trace reacts later"), ("control", "Trainer control conflicts")), issue)
    controller_options = options((("computer", "Training app / computer"), ("watch", "Watch / bike computer"), ("phone", "Phone / training app"), ("none", "No resistance controller")), controller)
    content = f'''<h1>Find where your power meters disagree.</h1><p class="intro">Record the same ride from each source. Compare the time traces and measured stages, then decide what to test next.</p><div class="layout"><section aria-labelledby="upload-title"><h2 id="upload-title">Compare recordings</h2><form action="/compare" method="post" enctype="multipart/form-data"><input type="hidden" name="token" value="{_escape(token)}"><div class="field"><label for="reference-file">Reference recording</label><span class="hint" id="files-help">A reference for relative differences, not a calibration standard. Select a FIT or CSV file.</span><input id="reference-file" name="files" type="file" accept=".fit,.csv" required aria-describedby="files-help"></div><div class="field"><label for="files">Comparison recordings</label><span class="hint" id="comparison-help">One to five FIT or CSV files from the same ride. Keep all files under 50 MB combined.</span><input id="files" name="files" type="file" accept=".fit,.csv" multiple required aria-describedby="comparison-help"></div><div class="field"><label for="windows">Measured stage windows <span class="muted">(optional)</span></label><span class="hint" id="windows-help">Start:end seconds from the reference start, with the end excluded. Pick the steady middle of each stage, after resistance settles.</span><input id="windows" name="windows" placeholder="180:300, 420:540" aria-describedby="windows-help"></div><details><summary>Clock settings and elapsed CSV</summary><div class="field"><label for="offsets">Explicit clock shifts</label><span class="hint" id="offsets-help">One filename=seconds per line. Use whole seconds. Positive values move that recording later. Nothing is shifted automatically.</span><textarea id="offsets" name="offsets" placeholder="meter.csv=2" aria-describedby="offsets-help"></textarea></div><div class="field"><label for="starts">Start times for elapsed CSV</label><span class="hint" id="starts-help">A CSV with elapsed seconds needs its recording start. Use filename=ISO timestamp with timezone, one per line.</span><textarea id="starts" name="starts" placeholder="meter.csv=2026-01-01T12:00:00Z" aria-describedby="starts-help"></textarea></div></details><button type="submit">Compare recordings</button><p class="hint">Uploads are temporary and removed after analysis. The resulting report stays in your browser. Save it with your browser or export HTML from the CLI.</p></form></section><section aria-labelledby="recipe-title"><h2 id="recipe-title">Make the test useful</h2><form action="/" method="get"><div class="row"><div class="field"><label for="issue">What is happening?</label><select id="issue" name="issue">{issue_options}</select></div><div class="field"><label for="controller">Who controls resistance?</label><select id="controller" name="controller">{controller_options}</select></div></div><div class="field"><label for="meters">Equipment <span class="muted">(optional)</span></label><input id="meters" name="meters" value="{_escape(meters)}" placeholder="Trainer, crank meter, head unit"></div><button class="secondary" type="submit">Update recording recipe</button></form><ol class="protocol">{steps}</ol><p class="note">Keep the original files. Record each sensor directly and note the resistance controller, warm-up, zero-offset procedure, connection channel, and any power matching.</p></section></div>'''
    return _document("Compare recordings", content)


def _trace_chart(sources: list[dict]) -> str:
    points = [(point[0], point[1]) for source in sources for point in source.get("plot", []) if len(point) >= 2 and isinstance(point[0], (int, float)) and math.isfinite(point[0]) and isinstance(point[1], (int, float)) and math.isfinite(point[1])]
    if not points:
        return '<p>No valid power samples are available for a trace.</p>'
    start, end = min(p[0] for p in points), max(p[0] for p in points)
    maximum = max(100, math.ceil(max(p[1] for p in points) / 100) * 100)
    minimum = min(0, math.floor(min(p[1] for p in points) / 100) * 100)
    width, height, left, top, right, bottom = 1040, 370, 64, 26, 22, 58
    span = max(1, end - start)
    x = lambda seconds: left + (seconds - start) / span * (width - left - right)
    y = lambda power: top + (maximum - power) / (maximum - minimum) * (height - top - bottom)
    shapes = []
    for i in range(5):
        power = minimum + (maximum - minimum) * i / 4
        level = y(power)
        shapes.append(f'<line x1="{left}" y1="{level:.2f}" x2="{width-right}" y2="{level:.2f}" stroke="#c6ccc5" stroke-width=".7"/><text class="axis" x="{left-10}" y="{level+4:.2f}" text-anchor="end">{power:.0f}</text>')
    for i in range(6):
        seconds = start + span * i / 5
        shapes.append(f'<text class="axis" x="{x(seconds):.2f}" y="{height-bottom+26}" text-anchor="middle">{seconds / 60:.1f}</text>')
    shapes.append(f'<text class="axis" x="{left}" y="15">Power (W)</text><text class="axis" x="{width/2}" y="{height-6}" text-anchor="middle">Minutes from reference start</text>')
    legends = []
    patterns = ("", "", "8 4", "2 4", "12 4 2 4", "5 3 2 3")
    for index, source in enumerate(sources):
        color = "#202c2c" if index == 0 else "#096b66"
        dash = patterns[index % len(patterns)]
        path, previous = [], None
        for point in source.get("plot", []):
            if len(point) < 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point[:2]):
                previous = None
                continue
            seconds, power = point[:2]
            command = "M" if previous is None or seconds - previous > 2.5 else "L"
            path.append(f"{command}{x(seconds):.2f},{y(power):.2f}")
            previous = seconds
        label = _escape(source.get("name", f"Recording {index+1}"))
        shapes.append(f'<path d="{" ".join(path)}" fill="none" stroke="{color}" stroke-width="1.6" stroke-dasharray="{dash}" stroke-linejoin="round"><title>{label}</title></path>')
        legends.append(f'<li><svg width="30" height="12" aria-hidden="true"><line x1="0" y1="6" x2="30" y2="6" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/></svg>{index+1}. {label}{" (reference)" if index == 0 else ""}</li>')
    return f'<ul class="legend">{"".join(legends)}</ul><div class="chart-scroll"><svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-labelledby="chart-title chart-desc"><title id="chart-title">Recorded power over time</title><desc id="chart-desc">Raw power traces on the reference clock. Different dashes identify recordings. Lines stop at missing readings and gaps longer than 2.5 seconds. Numerical comparisons follow below.</desc>{"".join(shapes)}</svg></div><p class="note">Raw samples, no smoothing. Missing samples and gaps longer than 2.5 seconds break the line. Zeros remain visible. A possible timing lag is diagnostic only and is never applied to this plot.</p>'


def render_report(result: dict) -> str:
    """Produce a self-contained report without remote assets or hidden clock fitting."""
    sources = result.get("sources", [])
    rows, alerts, timing = [], [], []
    for comparison in result.get("comparisons", []):
        name = _escape(comparison.get("name", "Recording"))
        sets = [("Whole recording", comparison.get("whole", {}))]
        for window in comparison.get("windows", []):
            seconds = window.get("seconds", ())
            label = f"{seconds[0]:g}–{seconds[1]:g} s" if len(seconds) == 2 else "Measured stage"
            if window.get("stage"):
                label += f" · {window['stage']}"
            sets.append((label, window))
        for label, metrics in sets:
            rows.append(f'<tr><td>{name}<br><span class="muted">{_escape(label)}</span></td><td>{_number(metrics.get("reference_w"))} W</td><td>{_number(metrics.get("comparison_w"))} W</td><td>{_number(metrics.get("difference_w"))} W</td><td>{_number(metrics.get("difference_percent"))}%</td><td>{_number(metrics.get("rmse_w"))} W</td><td>{_number(metrics.get("reference_sd_w"))} / {_number(metrics.get("comparison_sd_w"))} W</td><td>{_number(metrics.get("coverage_percent"))}%</td><td>{_number(metrics.get("paired_time_coverage_percent"))}%</td><td>{_number(metrics.get("samples"), 0)}</td></tr>')
        alerts.extend(f"{comparison.get('name', 'Recording')}: {alert}" for alert in comparison.get("alerts", []))
        lag = comparison.get("lag", {})
        lag_seconds = lag.get("best_comparison_later_seconds")
        if lag_seconds is not None:
            timing.append(f'{comparison.get("name", "Recording")}: diagnostic lag candidate {_number(lag_seconds)} s, {_number(lag.get("shared_samples"), 0)} shared samples. Not applied. Status: {lag.get("status", "unspecified")}.')
        elif lag:
            timing.append(f'{comparison.get("name", "Recording")}: lag status {lag.get("status", "unavailable")}.')
    provenance = []
    for index, source in enumerate(sources):
        alerts.extend(f"{source.get('name', 'Recording')}: {warning}" for warning in source.get("warnings", []))
        devices = source.get("devices", [])
        device_text = "; ".join(str(device) for device in devices) if isinstance(devices, list) else str(devices)
        provenance.append(f'<div class="source"><h3>{index+1}. {_escape(source.get("name", "Recording"))}</h3><dl><dt>Start</dt><dd>{_escape(source.get("start", "Unavailable"))}</dd><dt>End</dt><dd>{_escape(source.get("end", "Unavailable"))}</dd><dt>Records</dt><dd>{_escape(source.get("records", "Unavailable"))}</dd><dt>Clock shift</dt><dd>{_number(source.get("offset_seconds", source.get("offset", 0)))} s, explicit only</dd><dt>Power field</dt><dd>{_escape(source.get("selected_power_field", "power"))}</dd><dt>Fields found</dt><dd>{_escape(", ".join(source.get("available_power_fields", [])) or "Not recorded")}</dd><dt>Devices</dt><dd>{_escape(device_text or "Not recorded")}</dd></dl><p class="hash">SHA-256: {_escape(source.get("sha256", "Unavailable"))}</p></div>')
    alert_html = '<div class="alerts"><h3>Data quality</h3><ul>' + "".join(f"<li>{_escape(alert)}</li>" for alert in dict.fromkeys(alerts)) + "</ul></div>" if alerts else '<p class="note">No data-quality alerts were returned. This does not establish that either meter is accurate.</p>'
    guidance = result.get("guidance", [])
    protocol = result.get("protocol", [])
    content = f'''<h1>Your power comparison.</h1><p class="intro">Reference: {_escape(result.get("reference", sources[0].get("name", "Unavailable") if sources else "Unavailable"))}. Differences are relative to this recording. They cannot prove which device measures true power.</p><section aria-labelledby="traces-title"><h2 id="traces-title">Power over time</h2>{_trace_chart(sources)}</section><section aria-labelledby="results-title"><h2 id="results-title">Whole ride &amp; measured stages</h2><div class="table-wrap"><table><caption>Positive differences mean the comparison records higher power. Means and errors use shared valid samples. Paired / ref is the share of reference power samples with a valid match. Time coverage is the share of elapsed interval seconds with a valid pair; gaps in both files reduce it. RMSE is the typical size of sample-by-sample disagreement. SD (standard deviation) measures power variability within the selected interval.</caption><thead><tr><th scope="col">Recording / stage</th><th scope="col">Reference</th><th scope="col">Comparison</th><th scope="col">Difference</th><th scope="col">Difference %</th><th scope="col">RMSE</th><th scope="col">SD ref / comparison</th><th scope="col">Paired / ref</th><th scope="col">Time coverage</th><th scope="col">Samples</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>{alert_html}</section><section><h2>What to test next</h2><ul>{"".join(f"<li>{_escape(line)}</li>" for line in guidance)}</ul>{f'<h3>Recording recipe</h3><ol>{"".join(f"<li>{_escape(line)}</li>" for line in _protocol_lines(protocol))}</ol>' if protocol else ''}<p class="note">Power measured at the pedals or crank and at a trainer can differ through drivetrain loss. Sensor settings, temperature, zero offset, cadence, smoothing, and dropouts can also change the comparison. Use a controlled repeat before changing training zones.</p></section><section><h2>Time alignment &amp; provenance</h2><p>Method: {_escape(result.get("method", "Timestamp intersection; no automatic shift"))}.</p><ul>{"".join(f"<li>{_escape(line)}</li>" for line in timing)}</ul><div class="sources">{"".join(provenance)}</div><p class="note">Keep these hashes with the original recordings. Device metadata identifies what a file reports, not necessarily every sensor used by its recorder. The local upload uses the native power field; use CLI --power-field to compare a FIT developer power channel.</p></section><a class="back" href="/">Compare another recording</a>'''
    return _document("Comparison report", content, report=True)


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _number(value: object, digits: int = 1, suffix: str = "") -> str:
    if not isinstance(value, (float, int)) or not math.isfinite(value):
        return "Unavailable"
    return f"{value:,.{digits}f}{suffix}"


def _pairs(value: str, *, timestamps: bool = False) -> dict:
    result = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        name, separator, raw = line.partition("=")
        if not separator or not name.strip() or name.strip() in result:
            raise ValueError("Use one unique filename=value entry per line.")
        if timestamps:
            result[name.strip()] = raw.strip()
        else:
            offset = float(raw.strip())
            if not math.isfinite(offset) or abs(offset) > 86400:
                raise ValueError("Clock shifts must be finite seconds within one day.")
            result[name.strip()] = offset
    return result


def _windows(value: str) -> list[tuple[float, float]]:
    result = []
    for item in value.replace("\n", ",").split(","):
        if not item.strip():
            continue
        pieces = item.strip().split(":")
        if len(pieces) != 2:
            raise ValueError("Stage windows use start:end seconds, for example 180:300.")
        start, end = map(float, pieces)
        if not all(math.isfinite(v) for v in (start, end)) or start < 0 or end <= start:
            raise ValueError("Each stage must end after its non-negative start time.")
        result.append((start, end))
    if len(result) > 30:
        raise ValueError("Use at most 30 measured stages.")
    return result


def make_server(host: str = "127.0.0.1", port: int = 8765) -> HTTPServer:
    """Construct a local server; expose separately for meaningful HTTP tests."""
    if host != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError("The upload workspace must bind to a loopback address.")
        except ValueError as error:
            raise ValueError("Use a loopback address such as 127.0.0.1.") from error
    if ":" in host:
        raise ValueError("Use IPv4 loopback 127.0.0.1 or localhost.")
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            # Filenames and uploaded content do not belong in terminal logs.
            pass

        def _allowed(self) -> bool:
            actual_port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}", f"{host}:{actual_port}"}
            requested = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            return requested in hosts and (origin is None or origin == f"http://{requested}")

        def _send(self, status: int, page: str) -> None:
            payload = page.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            if not self._allowed():
                self._send(403, _error_page("This workspace accepts requests from its own local address."))
                return
            target = urlsplit(self.path)
            if target.path != "/":
                self._send(404, _error_page("That page does not exist. Return to the upload workspace."))
                return
            from .core import recommend_protocol

            query = parse_qs(target.query)
            issue = query.get("issue", ["mismatch"])[0]
            controller = query.get("controller", ["computer"])[0]
            meters = query.get("meters", [""])[0]
            try:
                protocol = recommend_protocol(issue=issue, controller=controller, meters=tuple(v.strip() for v in meters.split(",") if v.strip()))
                self._send(200, render_upload(token, protocol, issue, controller, meters))
            except ValueError:
                self._send(400, _error_page("Choose a supported issue and controller, then try again."))

        def do_POST(self) -> None:
            if not self._allowed():
                self._send(403, _error_page("This workspace accepts requests from its own local address."))
                return
            if self.path != "/compare":
                self._send(404, _error_page("That upload route does not exist."))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send(400, _error_page("The upload has an invalid length."))
                return
            if length <= 0 or length > MAX_UPLOAD_BYTES:
                self._send(413, _error_page("Select up to six FIT or CSV files, under 50 MB combined."))
                return
            if self.headers.get("Transfer-Encoding"):
                self._send(400, _error_page("Chunked uploads are not supported."))
                return
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data") or "\r" in content_type or "\n" in content_type:
                self._send(400, _error_page("Use the file selection form to upload FIT or CSV files."))
                return
            self.connection.settimeout(30)
            try:
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("The upload was interrupted. Select your files again.")
                message = BytesParser(policy=policy.default).parsebytes(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body)
                if not message.is_multipart():
                    raise ValueError("The upload form is incomplete. Select your files again.")
                fields, files = {}, []
                for index, part in enumerate(message.iter_parts()):
                    if index >= 14:
                        raise ValueError("Use at most six files and the comparison settings in this form.")
                    if part.is_multipart():
                        raise ValueError("Nested upload forms are not supported.")
                    name = part.get_param("name", header="content-disposition")
                    filename = part.get_filename()
                    payload = part.get_payload(decode=True) or b""
                    if filename:
                        # MIME quoted strings consume backslashes. Inspect the raw
                        # header too so a Windows path cannot become a safe-looking name.
                        disposition = next((value for key, value in part.raw_items() if key.lower() == "content-disposition"), "")
                        if name != "files" or "\\" in disposition or "/" in filename or "\\" in filename or filename in (".", "..") or any(ord(c) < 32 for c in filename):
                            raise ValueError("Upload filenames must be simple basenames without paths.")
                        if len(filename) > 200 or Path(filename).suffix.lower() not in (".fit", ".csv"):
                            raise ValueError("Upload FIT or CSV files with filenames under 200 characters.")
                        if not payload:
                            raise ValueError("An uploaded file is empty. Select the original recording.")
                        files.append((filename, payload))
                    elif name:
                        if len(payload) > 8192 or name in fields:
                            raise ValueError("The upload contains duplicate or oversized form fields.")
                        fields[name] = payload.decode("utf-8")
                if not secrets.compare_digest(fields.get("token", "").encode(), token.encode()):
                    self._send(403, _error_page("Reload this local workspace before uploading."))
                    return
                if not 2 <= len(files) <= MAX_FILES:
                    raise ValueError("Select two to six simultaneous recordings.")
                names = [name for name, _ in files]
                if len(set(names)) != len(names):
                    raise ValueError("Each uploaded recording needs a different filename.")
                windows = _windows(fields.get("windows", ""))
                offsets = _pairs(fields.get("offsets", ""))
                starts = _pairs(fields.get("starts", ""), timestamps=True)
                if (set(offsets) | set(starts)) - set(names):
                    raise ValueError("Clock entries must match the uploaded filenames exactly.")
                from .core import compare_files

                with TemporaryDirectory(prefix="power-compare-") as temporary:
                    paths = []
                    for index, (filename, payload) in enumerate(files):
                        # Each file owns a directory: case-insensitive filesystems
                        # otherwise let Meter.csv silently overwrite meter.csv.
                        directory = Path(temporary) / str(index)
                        directory.mkdir()
                        path = directory / filename
                        path.write_bytes(payload)
                        paths.append(path)
                    try:
                        result = compare_files(paths, windows=windows, offsets=offsets, starts=starts)
                    except ValueError:
                        raise ValueError("The recordings could not be read. Check file format, timestamps, and whole-second clock shifts. CSV elapsed seconds need a start time with timezone.") from None
                    page = render_report(result)
                self._send(200, page)
            except ValueError as error:
                self._send(400, _error_page(str(error)))
            except (UnicodeError, OSError):
                # Parser exceptions can contain private local paths. Keep recovery local.
                self._send(400, _error_page("The recordings or comparison settings could not be read. Check file format, timestamps, clock entries, and stage windows, then try again."))
            except Exception:
                self._send(500, _error_page("The comparison failed. Return to the workspace and try the CLI for diagnostic details."))

    return HTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run until interrupted. Recordings live only for their analysis request."""
    with make_server(host, port) as server:
        print(f"Power Compare: http://{host}:{server.server_address[1]}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
