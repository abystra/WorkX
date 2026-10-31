"""API errors as RFC 9457 problem details with WorkX fields (Part 11 §3).

Handlers raise ``ApiError``; the API entrypoint renders it. Codes are stable identifiers that clients
switch on; ``detail`` is human-readable and never contains secrets.
"""

from __future__ import annotations

from typing import Any

_TITLES = {
    400: "Invalid request",
    401: "Authentication required",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    412: "Precondition failed",
    413: "Payload too large",
    422: "Unprocessable request",
    428: "Precondition required",
    429: "Too many requests",
    500: "Internal error",
    502: "Upstream error",
    503: "Service unavailable",
}

RETRYABLE_CODES = {"UPSTREAM_UNAVAILABLE", "RATE_LIMITED", "INTERNAL"}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        detail: str = "",
        *,
        data: dict[str, Any] | None = None,
        retryable: bool | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(f"{status} {code}: {detail}")
        self.status = status
        self.code = code
        self.detail = detail or _TITLES.get(status, "Error")
        self.data = data or {}
        self.retryable = code in RETRYABLE_CODES if retryable is None else retryable
        self.headers = headers or {}

    def problem(self, request_id: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": f"https://docs.workx.example/errors/{self.code.lower().replace('_', '-')}",
            "title": _TITLES.get(self.status, "Error"),
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
            "request_id": request_id,
            "retryable": self.retryable,
        }
        if self.data:
            body["data"] = self.data
        return body


def not_found(detail: str = "The resource does not exist or you do not have access to it.") -> ApiError:
    # 404 is also used for unauthorized reads so that existence is not disclosed (Part 11 §3).
    return ApiError(404, "NOT_FOUND", detail)


def forbidden(detail: str = "You do not have permission to do this.") -> ApiError:
    return ApiError(403, "FORBIDDEN", detail)


def validation(detail: str, data: dict[str, Any] | None = None) -> ApiError:
    return ApiError(400, "VALIDATION_FAILED", detail, data=data)


def conflict(code: str, detail: str, data: dict[str, Any] | None = None) -> ApiError:
    return ApiError(409, code, detail, data=data)


def unauthenticated(code: str = "UNAUTHENTICATED", detail: str = "Sign in to continue.") -> ApiError:
    return ApiError(401, code, detail)
