"""Refresh web.py's embedded brand images from the exact approved docs SVGs."""
from base64 import b64encode
from pathlib import Path
from textwrap import wrap

ROOT = Path(__file__).resolve().parents[1]
START = "# BEGIN GENERATED BRAND ASSETS\n"
END = "# END GENERATED BRAND ASSETS\n"
ASSETS = (
    ("PRODUCT_MARK", "readme-header.svg"),
    ("PRODUCT_TITLE", "readme-title.svg"),
    ("CASTOR_SIGNATURE", "castor-footer.svg"),
)


def main():
    target = ROOT / "src/power_compare/web.py"
    source = target.read_text(encoding="utf-8")
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("web.py must contain one generated brand assets block")
    before, _, tail = source.partition(START)
    _, _, after = tail.partition(END)
    lines = [
        "# Exact docs SVG bytes embedded as images: reports and installed wheels need no asset files.",
        "# Image documents isolate their adaptive styles from the workspace palette.",
    ]
    for constant, filename in ASSETS:
        encoded = b64encode((ROOT / "docs" / filename).read_bytes()).decode("ascii")
        lines.extend([
            f"# Source: docs/{filename}",
            f"{constant} = (",
            '    "data:image/svg+xml;base64,"',
            *[f'    "{chunk}"' for chunk in wrap(encoded, 100)],
            ")",
            "",
        ])
    updated = before + START + "\n".join(lines) + END + after
    if updated != source:
        target.write_text(updated, encoding="utf-8")
    print("Embedded web brand assets match docs SVGs.")


if __name__ == "__main__":
    main()
