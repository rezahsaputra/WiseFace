"""Error model mirroring Face++'s `error_message` failure shape (PRD §5.1).

Face++ returns an HTTP error with a single `error_message` string. We reproduce
that shape so caller code that branches on `error_message` keeps working. The
set of codes is deliberately small — the PRD specifies NO_FACE_DETECTED and
INVALID_IMAGE as the primary modes, plus the standard auth/argument codes.
"""
from __future__ import annotations


class CompareError(Exception):
    """Raised anywhere in the compare pipeline to short-circuit to a Face++-
    shaped error response."""

    def __init__(self, error_message: str, http_status: int = 400) -> None:
        super().__init__(error_message)
        self.error_message = error_message
        self.http_status = http_status


# --- Canonical codes (string values are the wire contract) ---
AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"   # bad/missing api_key|api_secret
MISSING_ARGUMENTS = "MISSING_ARGUMENTS"         # no image supplied for a slot
INVALID_IMAGE = "INVALID_IMAGE"                 # unreadable/malformed input
IMAGE_DOWNLOAD_FAILED = "IMAGE_ERROR_FAILED_TO_DOWNLOAD"  # image_url fetch failed
IMAGE_TOO_LARGE = "IMAGE_FILE_TOO_LARGE"        # over max_image_bytes
NO_FACE_DETECTED = "NO_FACE_DETECTED"           # no face found in an image
INTERNAL_ERROR = "INTERNAL_ERROR"               # unexpected server failure
# Worker is at capacity — load shed so the caller backs off + retries. Mirrors
# Face++'s own code/status (HTTP 403) so existing Face++ client retry logic works.
CONCURRENCY_LIMIT_EXCEEDED = "CONCURRENCY_LIMIT_EXCEEDED"


def auth_error() -> CompareError:
    return CompareError(AUTHENTICATION_ERROR, http_status=401)


def concurrency_limit_error() -> CompareError:
    return CompareError(CONCURRENCY_LIMIT_EXCEEDED, http_status=403)


def missing_arguments(slot: str) -> CompareError:
    # `slot` ("image1"/"image2") aids debugging; the wire code stays canonical.
    err = CompareError(MISSING_ARGUMENTS, http_status=400)
    err.slot = slot  # type: ignore[attr-defined]
    return err
