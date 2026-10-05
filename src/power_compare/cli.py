"""CLI for local power comparisons and reproducible next tests."""
import argparse
import json
import math
import sys
from pathlib import Path

from .core import compare_files, recommend_protocol


def _window(value):
    try:
        low, high = map(float, value.split(":"))
        if not all(math.isfinite(v) for v in (low, high)) or low < 0 or high <= low:
            raise ValueError
        return low, high
    except ValueError as error:
        raise argparse.ArgumentTypeError("Window requires finite 0 <= START < END") from error


def _assignments(values, numeric=False):
    result = {}
    for value in values:
        if "=" not in value:
            raise ValueError("Clock arguments require LABEL=VALUE")
        label, raw = value.rsplit("=", 1)
        if not label or not raw or label in result:
            raise ValueError("Clock arguments require unique nonempty labels and values")
        try:
            result[label] = float(raw) if numeric else raw
        except ValueError as error:
            raise ValueError("Clock offsets must be numeric seconds") from error
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    comparison = commands.add_parser("compare", help="Compare two to six original FIT/CSV files")
    comparison.add_argument("files", nargs="+", type=Path)
    comparison.add_argument("--window", action="append", type=_window, default=[], help="START:END seconds from reference start; exclusive end")
    comparison.add_argument("--offset", action="append", default=[], help="LABEL=SECONDS, add whole seconds to a source clock")
    comparison.add_argument("--start", action="append", default=[], help="LABEL=ISO, explicit recording start for elapsed CSV")
    comparison.add_argument("--power-field", action="append", default=[], help="LABEL=FIELD, explicitly select a CSV/FIT power channel")
    comparison.add_argument("--out", type=Path, help="New output prefix; writes JSON/HTML without overwriting")
    protocol = commands.add_parser("protocol", help="Print reproducible next-test guidance as JSON")
    protocol.add_argument("--issue", choices=("mismatch", "dropouts", "lag", "control"), default="mismatch")
    protocol.add_argument("--controller", choices=("computer", "watch", "phone", "none"), default="computer")
    protocol.add_argument("--meter", action="append", default=[])
    server = commands.add_parser("serve", help="Start local upload/report UI")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == "protocol":
            result = recommend_protocol(args.issue, args.controller, args.meter)
        elif args.command == "serve":
            from .web import serve
            serve(host=args.host, port=args.port)
            return 0
        else:
            outputs = [Path(str(args.out) + suffix) for suffix in (".json", ".html")] if args.out else []
            inputs = {path.resolve() for path in args.files}
            if any(path.exists() or path.is_symlink() or path.resolve() in inputs for path in outputs):
                raise ValueError("Output already exists or would overwrite an input")
            result = compare_files(args.files, args.window, _assignments(args.offset, True), starts=_assignments(args.start), power_fields=_assignments(args.power_field))
            if outputs:
                from .web import render_report
                bodies = (json.dumps(result, indent=2, allow_nan=False) + "\n", render_report(result))
                for path, body in zip(outputs, bodies):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("x", encoding="utf-8") as stream:
                        stream.write(body)
                print("Saved " + ", ".join(map(str, outputs)), file=sys.stderr)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
