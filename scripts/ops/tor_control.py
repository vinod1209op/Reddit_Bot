from microdose_study_bot.core.logging import UnifiedLogger
logger = UnifiedLogger('TorControl').get_logger()
#!/usr/bin/env python3
"""
Control Tor via the ControlPort to request a new circuit (NEWNYM).
Usage:
  python scripts/ops/tor_control.py 9054 "16:HASH"
"""

from __future__ import annotations

import socket
import sys


def _send(sock: socket.socket, line: str) -> str:
    sock.sendall(f"{line}\r\n".encode())
    return sock.recv(1024).decode().strip()


def request_newnym(control_port: int, hashed_password: str) -> None:
    with socket.create_connection(("127.0.0.1", control_port), timeout=10) as sock:
        auth = _send(sock, f'AUTHENTICATE "{hashed_password}"')
        if not auth.startswith("250"):
            raise RuntimeError(f"Auth failed: {auth}")
        resp = _send(sock, "SIGNAL NEWNYM")
        if not resp.startswith("250"):
            raise RuntimeError(f"NEWNYM failed: {resp}")
        _send(sock, "QUIT")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/ops/tor_control.py <control_port> [hashed_password]")
    port = int(sys.argv[1])
    password = sys.argv[2] if len(sys.argv) > 2 else ""
    if not password:
        raise SystemExit("Hashed password required (the 16:... string from tor --hash-password).")
    request_newnym(port, password)
    logger.info(f"Rotated Tor circuit via ControlPort {port}.")


if __name__ == "__main__":
    main()