"""
Purpose: Optional VPN manager helper for local runs.
Constraints: Requires provider CLI tools installed; disabled by default.
"""

# Imports
import subprocess
import time
from typing import Dict, Optional

try:
    import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore


# Public API
class VPNManager:
    def __init__(self) -> None:
        self.vpn_configs: Dict[str, Dict[str, str]] = {
            "netherlands": {
                "provider": "protonvpn",
                "server": "nl-free.protonvpn.com",
                "protocol": "udp",
            },
            "usa": {
                "provider": "windscribe",
                "server": "us-central.windscribe.com",
                "protocol": "udp",
            },
            "japan": {
                "provider": "protonvpn",
                "server": "jp-free.protonvpn.com",
                "protocol": "udp",
            },
        }

    def connect_to_vpn(self, location: str) -> Optional[dict]:
        """Connect to a VPN location using provider CLIs."""
        config = self.vpn_configs.get(location)
        if not config:
            raise ValueError(f"Unknown VPN location: {location}")

        if config["provider"] == "protonvpn":
            cmd = ["protonvpn-cli", "connect", "--cc", location[:2].upper()]
        elif config["provider"] == "windscribe":
            cmd = ["windscribe", "connect", config["server"]]
        else:
            raise ValueError(f"Unsupported VPN provider: {config['provider']}")

        subprocess.run(cmd, check=False)
        time.sleep(5)
        return self.verify_connection()

    def verify_connection(self) -> Optional[dict]:
        """Return IP metadata if available."""
        if requests is None:
            return None
        try:
            response = requests.get("https://ipinfo.io/json", timeout=5)
            return response.json()
        except Exception:
            return None
