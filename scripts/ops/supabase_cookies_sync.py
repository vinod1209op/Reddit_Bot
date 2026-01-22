#!/usr/bin/env python3
"""
Sync cookie bundle with Supabase Storage for CI runs.

Usage:
  python scripts/ops/supabase_cookies_sync.py download
  python scripts/ops/supabase_cookies_sync.py upload
"""

import argparse
import os
import sys
import zipfile
from pathlib import Path

import requests

from microdose_study_bot.core.utils.retry import retry


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def _storage_url(base_url: str, bucket: str, path: str) -> str:
    base_url = base_url.rstrip("/")
    path = path.lstrip("/")
    return f"{base_url}/storage/v1/object/{bucket}/{path}"


def _download_bundle() -> None:
    base_url = _require_env("SUPABASE_URL")
    service_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    bucket = os.getenv("SUPABASE_COOKIES_BUCKET", "").strip()
    if not bucket:
        bucket = os.getenv("SUPABASE_BUCKET", "automation-secrets").strip() or "automation-secrets"
    path = os.getenv("SUPABASE_COOKIES_PATH", "cookies/cookies_bundle.zip").strip() or "cookies/cookies_bundle.zip"

    dest_dir = Path("data")
    dest_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = Path("/tmp/cookies_bundle.zip")

    headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
    url = _storage_url(base_url, bucket, path)
    def _do_request():
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code >= 300:
            raise RuntimeError(f"{resp.status_code}: {resp.text}")
        return resp

    resp = retry(_do_request, attempts=3, base_delay=1.0)
    bundle_path.write_bytes(resp.content)
    if not zipfile.is_zipfile(bundle_path):
        # Some uploads are base64 text of a zip. Try decoding once.
        try:
            import base64

            decoded = base64.b64decode(resp.content, validate=True)
            bundle_path.write_bytes(decoded)
        except Exception:
            decoded = None

    if not zipfile.is_zipfile(bundle_path):
        preview = resp.content[:200]
        try:
            preview_text = preview.decode("utf-8", errors="replace")
        except Exception:
            preview_text = repr(preview)
        raise SystemExit(
            "Downloaded file is not a zip. "
            f"Check SUPABASE_BUCKET/SUPABASE_COOKIES_PATH. Preview: {preview_text}"
        )

    with zipfile.ZipFile(bundle_path, "r") as zf:
        zf.extractall(".")

    print(f"Downloaded cookies bundle from {bucket}/{path}")


def _upload_bundle() -> None:
    base_url = _require_env("SUPABASE_URL")
    service_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    bucket = os.getenv("SUPABASE_COOKIES_BUCKET", "").strip()
    if not bucket:
        bucket = os.getenv("SUPABASE_BUCKET", "automation-secrets").strip() or "automation-secrets"
    path = os.getenv("SUPABASE_COOKIES_PATH", "cookies/cookies_bundle.zip").strip() or "cookies/cookies_bundle.zip"

    data_dir = Path("data")
    cookie_files = sorted(data_dir.glob("cookies_*.pkl"))
    if not cookie_files:
        raise SystemExit("No cookie files found in data/ (cookies_*.pkl)")

    bundle_path = Path("/tmp/cookies_bundle.zip")
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in cookie_files:
            zf.write(file_path, arcname=str(file_path))

    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "application/zip",
        "x-upsert": "true",
    }
    url = _storage_url(base_url, bucket, path)
    def _do_request():
        with bundle_path.open("rb") as handle:
            resp = requests.post(url, headers=headers, data=handle, timeout=30)
        if resp.status_code == 409:
            with bundle_path.open("rb") as handle:
                resp = requests.put(url, headers=headers, data=handle, timeout=30)
        if resp.status_code >= 300:
            raise RuntimeError(f"{resp.status_code}: {resp.text}")
        return resp

    try:
        retry(_do_request, attempts=3, base_delay=1.0)
    except Exception as exc:
        raise SystemExit(f"Supabase upload failed: {exc}") from exc

    print(f"Uploaded cookies bundle to {bucket}/{path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync cookie bundle with Supabase Storage.")
    parser.add_argument("action", choices=["download", "upload"])
    args = parser.parse_args()

    if args.action == "download":
        _download_bundle()
    else:
        _upload_bundle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
