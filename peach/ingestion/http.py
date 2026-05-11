"""Thin HTTP wrapper used by every concrete source.

Centralised here so:

* every outbound call uses a sane timeout and the configured
  ``EDGAR_USER_AGENT`` header by default;
* HTTP-layer concerns (timeout, status-code → exception, encoding) live
  in one place — sources concentrate on parsing;
* unit tests can monkeypatch one function (`fetch_text`) to inject
  fixture data without each source defining its own seam.
"""

from __future__ import annotations

import httpx
import structlog

from peach.config.settings import get_settings
from peach.ingestion.base import NetworkError, network_retry

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Timeouts and limits
# ---------------------------------------------------------------------------
# 30 s total / 10 s connect is generous for an EOD-only workload — the
# rare slow SEC response shouldn't kill an ingest, but a truly hung
# connection should fail fast enough to keep a 530-ticker batch on
# schedule.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@network_retry
def fetch_text(url: str, *, user_agent: str | None = None) -> str:
    """GET ``url`` and return the response body as text.

    Parameters
    ----------
    url
        Fully-qualified HTTPS URL.  Plain HTTP URLs are auto-upgraded by
        httpx if the server cooperates.
    user_agent
        Override for the User-Agent header.  Defaults to the
        ``EDGAR_USER_AGENT`` setting because that string is also the
        polite identifier we want every other vendor to see — change in
        ``.env`` if needed.

    Returns
    -------
    str
        UTF-8-decoded response body.

    Raises
    ------
    NetworkError
        For 5xx responses and any httpx-level transport error.  Retry
        decorator picks these up.
    httpx.HTTPStatusError
        For 4xx responses.  Not retried — a 404 means the URL is wrong,
        not that the server is flaky.
    """
    headers = {"User-Agent": user_agent or get_settings().edgar_user_agent}
    log.debug("http.fetch.start", url=url)
    try:
        with httpx.Client(
            timeout=DEFAULT_TIMEOUT, headers=headers, follow_redirects=True
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        # All transport-level failures (timeouts, DNS, connection reset)
        # become NetworkError so tenacity retries them.
        log.warning("http.fetch.network_error", url=url, error=str(exc))
        raise NetworkError(str(exc)) from exc

    if response.is_server_error:
        # 5xx — retry-eligible.
        log.warning("http.fetch.server_error", url=url, status=response.status_code)
        raise NetworkError(f"HTTP {response.status_code} for {url}")

    response.raise_for_status()  # 4xx → HTTPStatusError, no retry
    log.debug("http.fetch.ok", url=url, bytes=len(response.content))
    return response.text


@network_retry
def fetch_bytes(url: str, *, user_agent: str | None = None) -> bytes:
    """Like :func:`fetch_text` but returns raw bytes.

    Used for CSVs that pandas wants to consume directly, and for any
    binary payloads.
    """
    headers = {"User-Agent": user_agent or get_settings().edgar_user_agent}
    log.debug("http.fetch.start", url=url)
    try:
        with httpx.Client(
            timeout=DEFAULT_TIMEOUT, headers=headers, follow_redirects=True
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        log.warning("http.fetch.network_error", url=url, error=str(exc))
        raise NetworkError(str(exc)) from exc

    if response.is_server_error:
        log.warning("http.fetch.server_error", url=url, status=response.status_code)
        raise NetworkError(f"HTTP {response.status_code} for {url}")

    response.raise_for_status()
    return response.content


__all__: list[str] = ["fetch_bytes", "fetch_text"]
