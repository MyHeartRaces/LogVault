import http.client
import io
import urllib.error
import unittest
from unittest import mock

from logvault.api import WarcraftLogsClient, retry_delay
from logvault.errors import DownloadCancelled, GraphQLError, WarcraftLogsError


class FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None):
        self.body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class ApiRetryTests(unittest.TestCase):
    def test_incomplete_read_is_retried(self):
        messages: list[str] = []
        client = WarcraftLogsClient(
            access_token="token",
            retry_attempts=2,
            retry_base_delay=0,
            retry_callback=messages.append,
        )

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = [
                http.client.IncompleteRead(b'{"partial"'),
                FakeResponse(b'{"ok": true}'),
            ]

            result = client._request_json("https://example.test/graphql", data=b"{}", headers={})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("Retrying", messages[0])

    def test_retryable_http_error_is_retried(self):
        client = WarcraftLogsClient(access_token="token", retry_attempts=2, retry_base_delay=0)
        http_error = urllib.error.HTTPError(
            "https://example.test/graphql",
            503,
            "Service Unavailable",
            {},
            io.BytesIO(b"temporary"),
        )

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = [http_error, FakeResponse(b'{"ok": true}')]

            result = client._request_json("https://example.test/graphql", data=b"{}", headers={})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)

    def test_non_retryable_http_error_fails_once(self):
        client = WarcraftLogsClient(access_token="token", retry_attempts=3, retry_base_delay=0)
        http_error = urllib.error.HTTPError(
            "https://example.test/oauth",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b"bad credentials"),
        )

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = http_error

            with self.assertRaises(WarcraftLogsError):
                client._request_json("https://example.test/oauth", data=b"{}", headers={})

        self.assertEqual(urlopen.call_count, 1)

    def test_retry_after_caps_delay(self):
        self.assertEqual(retry_delay(1, base_delay=1, max_delay=5, retry_after="9"), 5)

    def test_cancelled_request_does_not_open_connection(self):
        client = WarcraftLogsClient(access_token="token", cancel_check=lambda: True)

        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(DownloadCancelled):
                client._request_json("https://example.test/graphql", data=b"{}", headers={})

        urlopen.assert_not_called()

    def test_metadata_keystone_field_fallback_keeps_full_metadata(self):
        class FakeClient(WarcraftLogsClient):
            def __init__(self):
                super().__init__(access_token="token")
                self.calls = 0

            def graphql(self, query, variables=None):
                self.calls += 1
                if "keystoneLevel" in query:
                    raise GraphQLError('Cannot query field "keystoneLevel" on type "ReportFight".')
                return {
                    "reportData": {
                        "report": {
                            "code": "abc",
                            "zone": {"name": "Sporefall"},
                            "masterData": {"actors": [], "abilities": []},
                            "fights": [{"id": 1, "difficulty": 5}],
                        }
                    }
                }

        client = FakeClient()

        report = client.fetch_report_metadata("abc")

        self.assertEqual(client.calls, 2)
        self.assertEqual(report["zone"]["name"], "Sporefall")
        self.assertIsNone(report["fights"][0]["keystoneLevel"])


if __name__ == "__main__":
    unittest.main()
