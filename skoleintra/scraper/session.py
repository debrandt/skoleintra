"""Persistent requests.Session wrapper for ForældreIntra.

Saves the cookie jar to disk so that subsequent runs can reuse an
authenticated session without re-logging in every time.
"""

import logging
import os
import pickle
from typing import Any

import requests

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "da,en-US;q=0.7,en;q=0.3",
}

_REQUEST_TIMEOUT = 30  # seconds


class PortalSession:
    """Thin wrapper around :class:`requests.Session` that persists cookies.

    Parameters
    ----------
    hostname:
        School hostname, e.g. ``example.foraldreintra.dk``.
    state_dir:
        Directory where the cookie jar and state are stored.
    """

    def __init__(self, hostname: str, state_dir: str) -> None:
        self.hostname = hostname
        self.state_dir = state_dir
        self._session = requests.Session()
        self._session.headers.update(_DEFAULT_HEADERS)
        self._load_cookies()

    # ------------------------------------------------------------------
    # Cookie persistence
    # ------------------------------------------------------------------

    def _cookie_path(self) -> str:
        os.makedirs(self.state_dir, exist_ok=True)
        return os.path.join(self.state_dir, f"{self.hostname}.cookies")

    def _load_cookies(self) -> None:
        path = self._cookie_path()
        if os.path.isfile(path):
            try:
                with open(path, "rb") as fh:
                    jar = pickle.load(fh)
                self._session.cookies.update(jar)
                logger.debug("Loaded cookies from %s", path)
            except Exception as exc:
                logger.warning("Could not load cookies from %s: %s", path, exc)

    def save_cookies(self) -> None:
        path = self._cookie_path()
        try:
            with open(path, "wb") as fh:
                pickle.dump(self._session.cookies, fh)
            logger.debug("Saved cookies to %s", path)
        except Exception as exc:
            logger.warning("Could not save cookies to %s: %s", path, exc)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def abs_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"https://{self.hostname}{path}"

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        url = self.abs_url(url)
        logger.debug("GET %s", url)
        kwargs.setdefault("timeout", _REQUEST_TIMEOUT)
        resp = self._session.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        url = self.abs_url(url)
        logger.debug("POST %s", url)
        kwargs.setdefault("timeout", _REQUEST_TIMEOUT)
        resp = self._session.post(url, **kwargs)
        resp.raise_for_status()
        return resp

    def save_debug_artifact(self, name: str, content: str | bytes) -> str:
        """Write *content* to ``<state_dir>/debug_<name>`` for post-mortem inspection.

        Returns the path where the artifact was written.
        """
        os.makedirs(self.state_dir, exist_ok=True)
        path = os.path.join(self.state_dir, f"debug_{name}")
        mode = "w" if isinstance(content, str) else "wb"
        with open(path, mode) as fh:
            fh.write(content)
        logger.info("Debug artifact saved to %s", path)
        return path
