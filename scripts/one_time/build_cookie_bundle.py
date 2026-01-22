#!/usr/bin/env python3
"""
Build a base64-encoded zip of cookie files under data/.

Usage:
  python scripts/one_time/build_cookie_bundle.py > cookies_bundle.b64
  python scripts/one_time/build_cookie_bundle.py --output cookies_bundle.b64
"""
import argparse
import base64
import io
import sys
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Bundle data/*.pkl into a base64 zip.")
    parser.add_argument("--output", default="", help="Write base64 output to a file.")
    args = parser.parse_args()

    data_dir = Path("data")
    if not data_dir.exists():
        raise SystemExit("data/ directory not found.")

    cookie_files = sorted(data_dir.glob("*.pkl"))
    if not cookie_files:
        raise SystemExit("No .pkl files found under data/.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in cookie_files:
            zf.write(path, arcname=str(path))

    raw_zip = buffer.getvalue()
    encoded = base64.b64encode(raw_zip).decode("ascii")
    if args.output:
        output_path = Path(args.output)
        if output_path.suffix.lower() == ".zip":
            output_path.write_bytes(raw_zip)
            print(f"Wrote zip bundle to {output_path}")
        else:
            output_path.write_text(encoded, encoding="utf-8")
            print(f"Wrote base64 bundle to {output_path}")
    else:
        sys.stdout.write(encoded)


if __name__ == "__main__":
    main()
