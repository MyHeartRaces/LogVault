from __future__ import annotations

import base64
import gzip
import http.client
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .errors import ConfigurationError, DownloadCancelled, GraphQLError, WarcraftLogsError


OAUTH_TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
GRAPHQL_URL = "https://www.warcraftlogs.com/api/v2/client"
DEFAULT_RETRY_ATTEMPTS = 8
DEFAULT_RETRY_BASE_DELAY = 1.0
DEFAULT_RETRY_MAX_DELAY = 30.0
RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}
RETRYABLE_TRANSPORT_ERRORS = (
    http.client.IncompleteRead,
    http.client.RemoteDisconnected,
    socket.timeout,
    TimeoutError,
    ConnectionError,
)


REPORT_METADATA_QUERY = """
query ReportMetadata($code: String!, $allowUnlisted: Boolean!) {
  reportData {
    report(code: $code, allowUnlisted: $allowUnlisted) {
      code
      title
      startTime
      endTime
      owner {
        name
      }
      zone {
        id
        name
      }
      fights {
        id
        encounterID
        name
        difficulty
        kill
        startTime
        endTime
        bossPercentage
        fightPercentage
        lastPhase
      }
      masterData(translate: true) {
        actors {
          id
          gameID
          name
          petOwner
          type
          subType
          server
        }
        abilities {
          gameID
          name
          type
        }
      }
    }
  }
}
"""


REPORT_METADATA_MINIMAL_QUERY = """
query ReportMetadataMinimal($code: String!, $allowUnlisted: Boolean!) {
  reportData {
    report(code: $code, allowUnlisted: $allowUnlisted) {
      code
      title
      startTime
      endTime
      fights {
        id
        encounterID
        name
        difficulty
        kill
        startTime
        endTime
      }
    }
  }
}
"""


REPORT_EVENTS_QUERY = """
query ReportEvents(
  $code: String!,
  $allowUnlisted: Boolean!,
  $dataType: EventDataType!,
  $fightIDs: [Int],
  $startTime: Float,
  $endTime: Float,
  $limit: Int!,
  $filterExpression: String
) {
  reportData {
    report(code: $code, allowUnlisted: $allowUnlisted) {
      events(
        dataType: $dataType,
        fightIDs: $fightIDs,
        startTime: $startTime,
        endTime: $endTime,
        limit: $limit,
        filterExpression: $filterExpression
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""


REPORT_TABLE_QUERY = """
query ReportTable(
  $code: String!,
  $allowUnlisted: Boolean!,
  $dataType: TableDataType!,
  $fightIDs: [Int]
) {
  reportData {
    report(code: $code, allowUnlisted: $allowUnlisted) {
      table(dataType: $dataType, fightIDs: $fightIDs)
    }
  }
}
"""


CHARACTER_RECENT_REPORTS_QUERY = """
query CharacterRecentReports(
  $name: String!,
  $serverSlug: String!,
  $serverRegion: String!,
  $limit: Int!,
  $page: Int!
) {
  characterData {
    character(name: $name, serverSlug: $serverSlug, serverRegion: $serverRegion) {
      id
      canonicalID
      name
      recentReports(limit: $limit, page: $page) {
        data {
          code
          title
          startTime
          endTime
          zone {
            id
            name
          }
        }
        total
        per_page
        current_page
        last_page
        has_more_pages
      }
    }
  }
}
"""


CHARACTER_RECENT_REPORTS_MINIMAL_QUERY = """
query CharacterRecentReportsMinimal(
  $name: String!,
  $serverSlug: String!,
  $serverRegion: String!,
  $limit: Int!,
  $page: Int!
) {
  characterData {
    character(name: $name, serverSlug: $serverSlug, serverRegion: $serverRegion) {
      id
      canonicalID
      name
      recentReports(limit: $limit, page: $page) {
        data {
          code
          title
          startTime
          endTime
        }
      }
    }
  }
}
"""


@dataclass
class EventPage:
    data: list[dict[str, Any]]
    next_page_timestamp: int | float | None


@dataclass
class CharacterReportPage:
    character: dict[str, Any]
    reports: list[dict[str, Any]]
    page: int
    has_more_pages: bool
    total: int | None


class WarcraftLogsClient:
    """Minimal Warcraft Logs v2 API client.

    The public v2 API uses OAuth client credentials and GraphQL. This client
    keeps the transport deliberately small so the project has no runtime deps.
    """

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        access_token: str | None = None,
        timeout: float = 60,
        token_url: str = OAUTH_TOKEN_URL,
        graphql_url: str = GRAPHQL_URL,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        retry_max_delay: float = DEFAULT_RETRY_MAX_DELAY,
        retry_callback: Callable[[str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = access_token
        self._token_expires_at = 0.0
        self.timeout = timeout
        self.token_url = token_url
        self.graphql_url = graphql_url
        self.retry_attempts = max(1, retry_attempts)
        self.retry_base_delay = max(0.0, retry_base_delay)
        self.retry_max_delay = max(0.0, retry_max_delay)
        self.retry_callback = retry_callback
        self.cancel_check = cancel_check
        self.ssl_context = build_ssl_context()

    def fetch_report_metadata(self, code: str, *, allow_unlisted: bool = True) -> dict[str, Any]:
        variables = {"code": code, "allowUnlisted": allow_unlisted}
        try:
            data = self.graphql(REPORT_METADATA_QUERY, variables)
            return data["reportData"]["report"]
        except GraphQLError as exc:
            if "Cannot query field" not in str(exc):
                raise
            data = self.graphql(REPORT_METADATA_MINIMAL_QUERY, variables)
            report = data["reportData"]["report"]
            report.setdefault("owner", None)
            report.setdefault("zone", None)
            report.setdefault("masterData", {"actors": [], "abilities": []})
            for fight in report.get("fights") or []:
                fight.setdefault("bossPercentage", None)
                fight.setdefault("fightPercentage", None)
                fight.setdefault("lastPhase", None)
            return report

    def fetch_table(
        self,
        code: str,
        data_type: str,
        *,
        fight_ids: list[int] | None,
        allow_unlisted: bool = True,
    ) -> Any:
        data = self.graphql(
            REPORT_TABLE_QUERY,
            {
                "code": code,
                "allowUnlisted": allow_unlisted,
                "dataType": data_type,
                "fightIDs": fight_ids,
            },
        )
        return data["reportData"]["report"]["table"]

    def fetch_event_page(
        self,
        code: str,
        data_type: str,
        *,
        fight_ids: list[int] | None,
        start_time: int | float | None,
        end_time: int | float | None,
        limit: int,
        allow_unlisted: bool = True,
        filter_expression: str | None = None,
    ) -> EventPage:
        data = self.graphql(
            REPORT_EVENTS_QUERY,
            {
                "code": code,
                "allowUnlisted": allow_unlisted,
                "dataType": data_type,
                "fightIDs": fight_ids,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
                "filterExpression": filter_expression,
            },
        )
        events = data["reportData"]["report"]["events"]
        return EventPage(
            data=list(events.get("data") or []),
            next_page_timestamp=events.get("nextPageTimestamp"),
        )

    def fetch_character_recent_reports(
        self,
        *,
        name: str,
        server_slug: str,
        server_region: str,
        limit: int = 100,
        page: int = 1,
    ) -> CharacterReportPage:
        variables = {
            "name": name,
            "serverSlug": server_slug,
            "serverRegion": server_region.lower(),
            "limit": limit,
            "page": page,
        }
        try:
            data = self.graphql(CHARACTER_RECENT_REPORTS_QUERY, variables)
        except GraphQLError as exc:
            if "Cannot query field" not in str(exc):
                raise
            data = self.graphql(CHARACTER_RECENT_REPORTS_MINIMAL_QUERY, variables)
        character = (data.get("characterData") or {}).get("character")
        if not character:
            raise WarcraftLogsError(
                f"Character not found: {name} on {server_region}/{server_slug}. "
                "Check character name, realm slug, and region."
            )
        pagination = character.get("recentReports") or {}
        reports = list(pagination.get("data") or [])
        return CharacterReportPage(
            character={key: value for key, value in character.items() if key != "recentReports"},
            reports=reports,
            page=int(pagination.get("current_page") or page),
            has_more_pages=bool(pagination.get("has_more_pages", len(reports) >= limit)),
            total=pagination.get("total"),
        )

    def iter_events(
        self,
        code: str,
        data_type: str,
        *,
        fight_ids: list[int] | None,
        start_time: int | float | None,
        end_time: int | float | None,
        limit: int,
        allow_unlisted: bool = True,
        filter_expression: str | None = None,
        max_pages: int | None = None,
    ):
        page_start = start_time
        page_count = 0
        previous_next: int | float | None = None

        while True:
            page = self.fetch_event_page(
                code,
                data_type,
                fight_ids=fight_ids,
                start_time=page_start,
                end_time=end_time,
                limit=limit,
                allow_unlisted=allow_unlisted,
                filter_expression=filter_expression,
            )
            page_count += 1
            for event in page.data:
                yield event

            next_timestamp = page.next_page_timestamp
            if next_timestamp is None:
                return
            if next_timestamp == previous_next or next_timestamp == page_start:
                raise WarcraftLogsError(
                    f"Pagination stopped for {data_type}: API returned the same nextPageTimestamp "
                    f"({next_timestamp}) twice."
                )
            if max_pages is not None and page_count >= max_pages:
                return

            previous_next = next_timestamp
            page_start = next_timestamp

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self.access_token()
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        response = self._request_json(
            self.graphql_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "LogVault/0.1",
            },
        )

        if response.get("errors"):
            messages = "; ".join(error.get("message", str(error)) for error in response["errors"])
            raise GraphQLError(messages)
        if "data" not in response:
            raise WarcraftLogsError(f"GraphQL response did not contain data: {response!r}")
        return response["data"]

    def access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 30:
            return self._access_token
        if self._access_token and self._token_expires_at == 0:
            return self._access_token
        if not self.client_id or not self.client_secret:
            raise ConfigurationError(
                "Missing Warcraft Logs credentials. Set WCL_CLIENT_ID and WCL_CLIENT_SECRET "
                "in .env/environment, or pass --client-id/--client-secret."
            )

        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("ascii")
        token_response = self._request_json(
            self.token_url,
            data=body,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "LogVault/0.1",
            },
        )

        access_token = token_response.get("access_token")
        if not access_token:
            raise WarcraftLogsError(f"OAuth response did not contain access_token: {token_response!r}")
        self._access_token = str(access_token)
        expires_in = int(token_response.get("expires_in") or 3600)
        self._token_expires_at = time.time() + expires_in
        return self._access_token

    def _request_json(
        self,
        url: str,
        *,
        data: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        request_headers = dict(headers)
        request_headers.setdefault("Accept-Encoding", "gzip, deflate")
        last_error: BaseException | None = None

        for attempt in range(1, self.retry_attempts + 1):
            self._raise_if_cancelled()
            request = urllib.request.Request(url, data=data, headers=request_headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                    raw = response.read()
                    content_encoding = response.headers.get("Content-Encoding", "").lower()
                self._raise_if_cancelled()
                return self._decode_json_response(url, raw, content_encoding)
            except urllib.error.HTTPError as exc:
                raw = read_error_body(exc)
                if exc.code in RETRYABLE_HTTP_CODES and attempt < self.retry_attempts:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    self._wait_before_retry(f"HTTP {exc.code} from Warcraft Logs", attempt, retry_after)
                    continue
                raise WarcraftLogsError(f"HTTP {exc.code} from {url}: {raw}") from exc
            except urllib.error.URLError as exc:
                if is_certificate_error(exc):
                    raise WarcraftLogsError(f"Request failed for {url}: {exc.reason}") from exc
                last_error = exc
                if attempt < self.retry_attempts:
                    self._wait_before_retry(f"request failed: {exc.reason}", attempt)
                    continue
                raise WarcraftLogsError(f"Request failed for {url}: {exc.reason}") from exc
            except RETRYABLE_TRANSPORT_ERRORS as exc:
                last_error = exc
                if attempt < self.retry_attempts:
                    self._wait_before_retry(f"connection interrupted: {exc}", attempt)
                    continue
                raise WarcraftLogsError(f"Request failed for {url}: {exc}") from exc
            except OSError as exc:
                if isinstance(exc, ssl.SSLCertVerificationError):
                    raise WarcraftLogsError(f"Request failed for {url}: {exc}") from exc
                last_error = exc
                if attempt < self.retry_attempts:
                    self._wait_before_retry(f"network error: {exc}", attempt)
                    continue
                raise WarcraftLogsError(f"Request failed for {url}: {exc}") from exc
            except ResponseDecodeError as exc:
                last_error = exc
                if attempt < self.retry_attempts:
                    self._wait_before_retry(str(exc), attempt)
                    continue
                raise WarcraftLogsError(str(exc)) from exc

        raise WarcraftLogsError(f"Request failed for {url}: {last_error}")

    def _decode_json_response(self, url: str, raw: bytes, content_encoding: str) -> dict[str, Any]:
        try:
            if content_encoding == "gzip":
                raw = gzip.decompress(raw)
            elif content_encoding == "deflate":
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            decoded = json.loads(raw.decode("utf-8"))
        except (gzip.BadGzipFile, EOFError, zlib.error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResponseDecodeError(f"Invalid JSON response from {url}: {raw[:500]!r}") from exc
        if not isinstance(decoded, dict):
            raise WarcraftLogsError(f"Expected JSON object from {url}, got {type(decoded).__name__}")
        return decoded

    def _wait_before_retry(self, reason: str, attempt: int, retry_after: str | None = None) -> None:
        delay = retry_delay(
            attempt,
            base_delay=self.retry_base_delay,
            max_delay=self.retry_max_delay,
            retry_after=retry_after,
        )
        next_attempt = attempt + 1
        if self.retry_callback:
            self.retry_callback(
                f"Warcraft Logs request failed ({reason}). "
                f"Retrying in {delay:g}s ({next_attempt}/{self.retry_attempts})..."
            )
        self._sleep_with_cancel(delay)

    def _sleep_with_cancel(self, delay: float) -> None:
        end = time.monotonic() + delay
        while True:
            self._raise_if_cancelled()
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.25, remaining))

    def _raise_if_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise DownloadCancelled("Download cancelled.")


class ResponseDecodeError(Exception):
    """Internal marker for transient response bodies that may be retried."""


def read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def is_certificate_error(exc: urllib.error.URLError) -> bool:
    reason = exc.reason
    return isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason)


def retry_delay(
    attempt: int,
    *,
    base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    max_delay: float = DEFAULT_RETRY_MAX_DELAY,
    retry_after: str | None = None,
) -> float:
    if retry_after:
        try:
            return min(max_delay, max(0.0, float(retry_after)))
        except ValueError:
            pass
    return min(max_delay, base_delay * (2 ** (attempt - 1)))


def build_ssl_context() -> ssl.SSLContext:
    cafile = find_ca_bundle()
    if cafile:
        return ssl.create_default_context(cafile=str(cafile))
    return ssl.create_default_context()


def find_ca_bundle() -> Path | None:
    env_names = ("WCL_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
    for name in env_names:
        value = os.getenv(name)
        if value and Path(value).is_file():
            return Path(value)

    try:
        import certifi
    except ImportError:
        pass
    else:
        certifi_path = Path(certifi.where())
        if certifi_path.is_file():
            return certifi_path

    for candidate in (
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "/opt/homebrew/etc/ca-certificates/cert.pem",
        "/opt/homebrew/etc/openssl@3/cert.pem",
        "/usr/local/etc/openssl@3/cert.pem",
        "/usr/local/etc/openssl/cert.pem",
    ):
        path = Path(candidate)
        if path.is_file():
            return path
    return None
