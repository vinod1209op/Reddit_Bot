"""
Purpose: Manage Tor proxy lifecycle for Selenium runs.
Constraints: Networking helper only; no posting logic.
"""

# Imports
import logging
import os
import requests
import subprocess
import time

from microdose_study_bot.core.utils.http import request_with_retry

logger = logging.getLogger(__name__)


# Public API
class TorProxy:
    def __init__(self):
        self.tor_process = None
        port = os.getenv("TOR_SOCKS_PORT", "9050").strip() or "9050"
        self.proxy_url = os.getenv("TOR_PROXY_URL", f"socks5://127.0.0.1:{port}").strip()

    def start(self) -> bool:
        """Start Tor proxy"""
        try:
            logger.info("Installing and starting Tor proxy...")
            subprocess.run(["sudo", "apt-get", "update"], capture_output=True, check=False)
            subprocess.run(["sudo", "apt-get", "install", "-y", "tor"], capture_output=True, check=False)

            self.tor_process = subprocess.Popen(
                ["tor", "--RunAsDaemon", "1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(10)

            if self.test_connection():
                logger.info("✓ Tor proxy started successfully")
                return True
            logger.error("Tor proxy failed to connect")
            return False
        except Exception as exc:
            logger.error(f"Failed to start Tor: {exc}")
            return False

    def test_connection(self) -> bool:
        """Test if Tor proxy is working."""
        try:
            response = request_with_retry(
                "GET",
                "http://httpbin.org/ip",
                proxies={"http": self.proxy_url, "https": self.proxy_url},
                timeout=10,
            )
            logger.info(f"Tor IP: {response.json().get('origin')}")
            return True
        except Exception as exc:
            logger.error(f"Tor test failed: {exc}")
            return False

    def get_new_ip(self) -> bool:
        """Restart Tor to rotate exit node."""
        try:
            self.stop()
            time.sleep(2)
            return self.start()
        except Exception as exc:
            logger.error(f"Failed to get new IP: {exc}")
            return False

    def stop(self) -> None:
        """Stop Tor proxy"""
        if self.tor_process:
            self.tor_process.terminate()
            self.tor_process.wait()
            self.tor_process = None
            logger.info("Tor proxy stopped")


# Singleton
tor_proxy = TorProxy()
