from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigurationError, GraphQLError, WarcraftLogsError


OAUTH_TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
GRAPHQL_URL = "https://www.warcraftlogs.com/api/v2/client"


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


@dataclass
class EventPage:
    data: list[dict[str, Any]]
    next_page_timestamp: int | float | None


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
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = access_token
        self._token_expires_at = 0.0
        self.timeout = timeout
        self.token_url = token_url
        self.graphql_url = graphql_url
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
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise WarcraftLogsError(f"HTTP {exc.code} from {url}: {raw}") from exc
        except urllib.error.URLError as exc:
            raise WarcraftLogsError(f"Request failed for {url}: {exc.reason}") from exc

        try:
            decoded = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise WarcraftLogsError(f"Invalid JSON response from {url}: {raw[:500]!r}") from exc
        if not isinstance(decoded, dict):
            raise WarcraftLogsError(f"Expected JSON object from {url}, got {type(decoded).__name__}")
        return decoded


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
