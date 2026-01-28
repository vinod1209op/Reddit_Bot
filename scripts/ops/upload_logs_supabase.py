from microdose_study_bot.core.logging import UnifiedLogger
logger = UnifiedLogger('UploadLogsSupabase').get_logger()
#!/usr/bin/env python3
"""
Upload scan logs to Supabase Storage.

Required env vars:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  SUPABASE_BUCKET

Optional env vars:
  SUPABASE_PREFIX (default: scan-results)
  SUPABASE_INCLUDE_LOG (default: 0) -> include logs/selenium_automation.log
"""

# Imports
import os
from pathlib import Path
from typing import List, Tuple

import requests
from microdose_study_bot.core.utils.http import post_with_retry

from microdose_study_bot.core.utils.retry import retry


# Helpers
def _get_env(name: str) -> str:
    return os.getenv(name, "").strip()


def _upload_file(url: str, key: str, bucket: str, object_path: str, file_path: Path) -> None:
    endpoint = f"{url}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "x-upsert": "true",
        "Content-Type": "application/octet-stream",
    }
    def _do_request():
        with file_path.open("rb") as handle:
            resp = post_with_retry(endpoint, headers=headers, data=handle, timeout=30)
        if resp.status_code >= 300:
            raise RuntimeError(f"{resp.status_code}: {resp.text}")
        return resp

    retry(_do_request, attempts=3, base_delay=1.0)


# Public API
def main() -> None:
    supabase_url = _get_env("SUPABASE_URL")
    supabase_key = _get_env("SUPABASE_SERVICE_ROLE_KEY")
    bucket = _get_env("SUPABASE_BUCKET")
    prefix = _get_env("SUPABASE_PREFIX") or "scan-results"
    include_log = _get_env("SUPABASE_INCLUDE_LOG") in ("1", "true", "yes", "y")

    if not supabase_url or not supabase_key or not bucket:
        raise SystemExit("Missing SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, or SUPABASE_BUCKET.")

    root = Path(__file__).resolve().parents[2]
    files: List[Tuple[str, Path]] = [
        (f"{prefix}/night_queue.json", root / "logs" / "night_queue.json"),
        (f"{prefix}/night_scan_summary.csv", root / "logs" / "night_scan_summary.csv"),
        (f"{prefix}/seen_posts.json", root / "data" / "seen_posts.json"),
        (f"{prefix}/account_status.json", root / "data" / "account_status.json"),
    ]
    if include_log:
        files.append((f"{prefix}/selenium_automation.log", root / "logs" / "selenium_automation.log"))

    uploaded = 0
    for object_path, file_path in files:
        if not file_path.exists():
            continue
        _upload_file(supabase_url, supabase_key, bucket, object_path, file_path)
        uploaded += 1

    logger.info(f"Uploaded {uploaded} file(s) to Supabase bucket '{bucket}' under '{prefix}/'.")


# Entry point
if __name__ == "__main__":
    main()