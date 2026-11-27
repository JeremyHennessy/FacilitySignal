"""Offline seam for one raw, conditional compact iQIES GET.

No HTTP client, Azure SDK, endpoint, credentials, or automatic redirects,
retries, decompression or fallback. The fixture receives one request and
supplies the actual status, uncombined headers and a framed response body.
A future transport must prove those properties on the wire independently.
"""

import re

from scripts.iqies_compact_release_contract import (
    BLOCK_BYTES,
    ObjectVersion,
    ReadbackRange,
    require,
)

_NAME = re.compile(r"iqies-services/[0-9a-f]{64}/(?:services\.sqlite3|manifest\.json)")
_ETAG = re.compile(r'"[!#-~]+"')
_HEADER = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_RELEVANT = {"content-length", "content-range", "etag", "transfer-encoding",
             "content-encoding", "content-type", "x-ms-structured-body"}


def _range_headers(rows):
    # The raw sequence must preserve even identically-valued duplicates.
    require(isinstance(rows, (tuple, list)), "raw range headers unavailable")
    out = {}
    for row in rows:
        require(isinstance(row, (list, tuple)) and len(row) == 2, "malformed range header")
        name, value = row
        require(isinstance(name, str) and _HEADER.fullmatch(name)
                and isinstance(value, str) and "\r" not in value and "\n" not in value,
                "malformed range header")
        name = name.lower()
        if name in _RELEVANT:
            require(name not in out, "duplicate range header")
            out[name] = value.strip(" \t")
    return out


def get_range_once(version, start, stop, request_once):
    """Return a validated range for an exact ObjectVersion; stop is exclusive.

    The injected fixture operation is called as
    `request_once("GET", exact_key, headers=...)` and returns a context manager
    holding `status`, uncombined `headers`, and `read(count)`. The reader
    must respect the verified Content-Length framing and may never fetch
    additional responses or decompress content. No socket or SDK is used.
    """
    require(isinstance(version, ObjectVersion)
            and isinstance(version.name, str) and _NAME.fullmatch(version.name)
            and isinstance(version.etag, str) and _ETAG.fullmatch(version.etag),
            "invalid versioned range identity")
    require(all(type(n) is int for n in (start, stop, version.size))
            and 0 <= start < stop <= version.size and stop - start <= BLOCK_BYTES,
            "invalid bounded range")
    length = stop - start
    headers = {"Range": f"bytes={start}-{stop-1}", "If-Match": version.etag,
               "Accept-Encoding": "identity"}
    with request_once("GET", version.name, headers=headers) as response:
        require(type(response.status) is int and response.status == 206,
                "range response must be 206")
        actual = _range_headers(response.headers)
        require(actual.get("content-length") == str(length)
                and actual.get("content-range") == f"bytes {start}-{stop-1}/{version.size}"
                and actual.get("etag") == version.etag, "range response metadata mismatch")
        require("transfer-encoding" not in actual and "x-ms-structured-body" not in actual
                and actual.get("content-encoding", "identity").lower() == "identity"
                and actual.get("content-type", "").split(";", 1)[0].strip().lower()
                != "multipart/byteranges",
                "unexpected response encoding")
        # No EOF probe beyond the Content-Length-delimited message or cap.
        body = response.read(length)
        require(type(body) is bytes and len(body) == length, "range body length mismatch")
        return ReadbackRange(version.name, actual["etag"], response.status,
                             start, stop, version.size, body)
    # An injected context manager must not suppress an invalid response.
    raise ValueError("unverified range response")
