from contextlib import contextmanager
from dataclasses import replace
from http.client import HTTPResponse
from io import BytesIO
from unittest import TestCase

from scripts import iqies_compact_release_contract as contract
from scripts import iqies_compact_wire_range as wire
from test_iqies_compact_release_contract import fixture


class InertSocket:
    """Give the standard HTTP parser a fixed response; never open a socket."""

    def __init__(self, response):
        self.buffer = BytesIO(response)

    def makefile(self, mode):
        assert mode == "rb"
        return self.buffer


class WireFixture:
    def __init__(self, data, status=206, headers=(), claimed_read=None):
        self.status = status
        self.headers = headers
        self.data = data
        self.claimed_read = claimed_read
        self.calls = []
        self.body_reads = []
        self.closed = 0

    @contextmanager
    def request_once(self, method, name, *, headers):
        self.calls.append((method, name, headers))
        # Parse the actual synthetic HTTP status line and repeated headers.
        raw = (f"HTTP/1.1 {self.status} Fixture\r\n" +
               "".join(f"{k}: {v}\r\n" for k, v in self.headers) + "\r\n").encode("ascii")
        with HTTPResponse(InertSocket(raw + self.data)) as parser:
            parser.begin()
            self.status = parser.status
            self.headers = parser.getheaders()
            self.parser = parser
            try:
                yield self
            finally:
                self.closed += 1

    def read(self, size):
        self.body_reads.append(size)
        if self.claimed_read is not None:
            return self.claimed_read
        return self.parser.read(size)


class CompactWireRangeTests(TestCase):
    def setUp(self):
        self.payload, self.manifest, r, n = fixture()
        self.plan = contract.release_plan(r, n)
        self.version = contract.ObjectVersion(self.plan.payload.name, len(self.payload), '"abc"')
        self.raw = [("Content-Length", "7"), ("Content-Range", f"bytes 5-11/{len(self.payload)}"),
                    ("ETag", '"abc"')]

    def test_actual_parsed_wire_range_and_exact_request(self):
        f = WireFixture(b"example", headers=self.raw)
        got = wire.get_range_once(self.version, 5, 12, f.request_once)
        self.assertEqual(got, contract.ReadbackRange(self.version.name, '"abc"', 206,
                                                     5, 12, len(self.payload), b"example"))
        self.assertEqual(f.calls, [("GET", self.version.name, {
            "Range": "bytes=5-11", "If-Match": '"abc"', "Accept-Encoding": "identity",
        })])
        self.assertEqual((f.body_reads, f.closed), ([7], 1))

    def test_short_or_invalid_reader_body_stops_after_one_request(self):
        for data, override in ((b"short", None), (b"", b"abcdefgh"), (b"", bytearray(b"example"))):
            with self.subTest(length=len(data), override=type(override)):
                f = WireFixture(data, headers=self.raw, claimed_read=override)
                with self.assertRaisesRegex(ValueError, "range body length mismatch"):
                    wire.get_range_once(self.version, 5, 12, f.request_once)
                self.assertEqual((len(f.calls), f.body_reads, f.closed), (1, [7], 1))

    def test_non_range_statuses_never_read_and_are_not_retried(self):
        for status in (200, 301, 404, 412, 416, 500):
            with self.subTest(status=status):
                f = WireFixture(b"example", status, self.raw + [("Location", "/not-followed")])
                with self.assertRaisesRegex(ValueError, "must be 206"):
                    wire.get_range_once(self.version, 5, 12, f.request_once)
                self.assertEqual((len(f.calls), f.body_reads, f.closed), (1, [], 1))

    def test_bad_or_ambiguous_wire_metadata_is_rejected_before_body_read(self):
        wrong = (
            self.raw[1:], self.raw + [("etag", '"abc"')],
            self.raw + [("content-length", "7")],
            self.raw[:1] + [("Content-Range", f"bytes 5-12/{len(self.payload)}"), self.raw[2]],
            self.raw[:1] + [("Content-Range", f"bytes 5-11/{len(self.payload)+1}"), self.raw[2]],
            self.raw[:2] + [("ETag", '"different"')],
            [("Content-Length", "8")] + self.raw[1:],
            self.raw + [("Content-Encoding", "gzip")],
            self.raw + [("Transfer-Encoding", "chunked")],
            self.raw + [("x-ms-structured-body", "XSM/1.0; properties=crc64")],
            self.raw + [("Content-Type", "multipart/byteranges; boundary=fixture")],
        )
        for headers in wrong:
            with self.subTest(headers=headers):
                f = WireFixture(b"example", headers=headers)
                with self.assertRaises(ValueError):
                    wire.get_range_once(self.version, 5, 12, f.request_once)
                self.assertEqual((len(f.calls), f.body_reads, f.closed), (1, [], 1))

    def test_invalid_key_version_or_request_size_never_calls_fixture(self):
        f = WireFixture(b"", headers=self.raw)
        cases = ((self.version, -1, 12), (self.version, 5, 5),
                 (self.version, 0, contract.BLOCK_BYTES+1), (self.version, 0, len(self.payload)+1),
                 (replace(self.version, name="unqualified-key"), 5, 12),
                 (replace(self.version, etag='W/"abc"'), 5, 12),
                 (replace(self.version, etag="*"), 5, 12))
        for version, start, stop in cases:
            with self.subTest(version=version, start=start, stop=stop), self.assertRaises(ValueError):
                wire.get_range_once(version, start, stop, f.request_once)
        self.assertEqual(f.calls, [])

    def test_checksum_contract_uses_only_expected_raw_ranges(self):
        parts = {self.plan.payload.name: self.payload, self.plan.manifest.name: self.manifest}
        versions = {name: contract.ObjectVersion(name, len(data), f'"id-{i}"')
                    for i, (name, data) in enumerate(parts.items())}
        calls = []

        def read_range(name, start, stop, *, if_match):
            version = versions[name]
            self.assertEqual(if_match, version.etag)
            data = parts[name]
            f = WireFixture(data[start:stop], headers=[
                ("Content-Length", str(stop-start)),
                ("Content-Range", f"bytes {start}-{stop-1}/{len(data)}"),
                ("ETag", version.etag),
            ])
            result = wire.get_range_once(version, start, stop, f.request_once)
            self.assertEqual((len(f.calls), f.body_reads, f.closed), (1, [stop-start], 1))
            calls.append((name, stop-start))
            return result

        result = contract.verify_pair_readback(self.plan, versions, read_range)
        self.assertEqual(result["objects_verified"], 2)
        self.assertEqual(result["bytes_verified"], len(self.payload) + len(self.manifest))
        b = contract.BLOCK_BYTES
        self.assertEqual(calls, [(self.plan.payload.name, b), (self.plan.payload.name, b),
                                 (self.plan.payload.name, 3),
                                 (self.plan.manifest.name, len(self.manifest))])

    def test_dropped_second_message_stops_entire_object_verification(self):
        calls = []

        def read_range(name, start, stop, *, if_match):
            self.assertEqual((name, if_match), (self.version.name, self.version.etag))
            calls.append(start)
            chunk = self.payload[start:stop] if start == 0 else b"truncated"
            f = WireFixture(chunk, headers=[
                ("Content-Length", str(stop-start)),
                ("Content-Range", f"bytes {start}-{stop-1}/{len(self.payload)}"),
                ("ETag", self.version.etag),
            ])
            try:
                return wire.get_range_once(self.version, start, stop, f.request_once)
            finally:
                self.assertEqual((len(f.calls), f.body_reads, f.closed), (1, [stop-start], 1))

        with self.assertRaisesRegex(ValueError, "range body length mismatch"):
            contract.verify_object_readback(self.plan.payload, self.version, read_range)
        self.assertEqual(calls, [0, contract.BLOCK_BYTES])
