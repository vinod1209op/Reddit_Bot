import sys
from pathlib import Path
from typing import TextIO


class _TeeStream:
    def __init__(self, primary: TextIO, secondary: TextIO) -> None:
        self._primary = primary
        self._secondary = secondary
        self.encoding = getattr(primary, "encoding", "utf-8")

    def write(self, data: str) -> int:
        written = 0
        for stream in (self._primary, self._secondary):
            try:
                written = stream.write(data)
            except Exception:
                continue
        return written

    def flush(self) -> None:
        for stream in (self._primary, self._secondary):
            try:
                stream.flush()
            except Exception:
                continue

    def isatty(self) -> bool:
        return bool(getattr(self._primary, "isatty", lambda: False)())


def enable_console_tee(log_path: str) -> None:
    """Mirror stdout/stderr to a log file (append)."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = path.open("a", encoding="utf-8")

    sys.stdout = _TeeStream(sys.stdout, log_handle)  # type: ignore[assignment]
    sys.stderr = _TeeStream(sys.stderr, log_handle)  # type: ignore[assignment]
