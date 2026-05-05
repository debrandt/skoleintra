"""Persistent requests.Session wrapper for ForældreIntra.

Saves the cookie jar to disk so that subsequent runs can reuse an
authenticated session without re-logging in every time.
"""

import logging
import os
import pickle
import time
from hashlib import sha1
from typing import Any

import requests
from requests.structures import CaseInsensitiveDict

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

    def _response_cache_dir(self) -> str:
        path = os.path.join(self.state_dir, "response-cache")
        os.makedirs(path, exist_ok=True)
        return path

    def _response_cache_path(self, url: str) -> str:
        digest = sha1(url.encode("utf-8")).hexdigest()
        return os.path.join(self._response_cache_dir(), f"{digest}.pickle")

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
        """Persist the session cookie jar to disk for reuse."""
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
        """Convert a portal-relative path into an absolute URL."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"https://{self.hostname}{path}"

    def get(
        self, url: str, *, cache_ttl_seconds: int | None = None, **kwargs: Any
    ) -> requests.Response:
        """Perform a GET request against the portal with default headers and timeout."""
        url = self.abs_url(url)
        logger.debug("GET %s", url)
        if cache_ttl_seconds is not None:
            cached = self._load_cached_response(url, cache_ttl_seconds)
            if cached is not None:
                logger.debug("GET cache hit %s", url)
                return cached
        kwargs.setdefault("timeout", _REQUEST_TIMEOUT)
        resp = self._session.get(url, **kwargs)
        resp.raise_for_status()
        if cache_ttl_seconds is not None:
            self._store_cached_response(url, resp)
        return resp

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        """Perform a POST request against the portal with default headers and timeout."""
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
        if isinstance(content, str):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        else:
            with open(path, "wb") as fh:
                fh.write(content)
        logger.info("Debug artifact saved to %s", path)
        return path

    def _load_cached_response(
        self, url: str, cache_ttl_seconds: int
    ) -> requests.Response | None:
        path = self._response_cache_path(url)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as fh:
                payload = pickle.load(fh)
        except Exception as exc:
            logger.warning("Could not load response cache %s: %s", path, exc)
            return None

        cached_at = payload.get("cached_at")
        if not isinstance(cached_at, (int, float)):
            return None
        if time.time() - cached_at > cache_ttl_seconds:
            return None

        response = requests.Response()
        response.status_code = int(payload.get("status_code", 200))
        response.url = str(payload.get("url") or url)
        self._set_response_content(response, payload.get("content") or b"")
        response.headers = CaseInsensitiveDict(payload.get("headers") or {})
        response.encoding = payload.get("encoding")
        return response

    def _store_cached_response(self, url: str, response: requests.Response) -> None:
        path = self._response_cache_path(url)
        payload = {
            "cached_at": time.time(),
            "url": response.url,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": response.content,
            "encoding": response.encoding,
        }
        try:
            with open(path, "wb") as fh:
                pickle.dump(payload, fh)
        except Exception as exc:
            logger.warning("Could not store response cache %s: %s", path, exc)

    @staticmethod
    def _set_response_content(response: requests.Response, content: bytes) -> None:
        # requests.Response has no public constructor for preloaded bodies.
        # Rehydrating the cached payload requires setting the internal buffer.
        response._content = content  # pylint: disable=protected-access
