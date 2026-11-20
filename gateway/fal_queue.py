"""Adapter for fal's queue API: submit a job, ask whether it has finished, collect its image.

The rest of the gateway talks to fal only through FalQueue.
Reference: https://docs.fal.ai/model-apis/model-endpoints/queue
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

__all__ = ["FalError", "FalQueue", "Image", "JobNotFound"]

QUEUE_URL = "https://queue.fal.run"
FINISHED = "COMPLETED"
CALL_TIMEOUT_SECONDS = 10
DOWNLOAD_TIMEOUT_SECONDS = 15


class FalError(Exception):
    """fal refused or failed a call; the message is fal's own explanation where it gave one."""

    def __init__(self, detail: str, *, status: int | None = None) -> None:
        super().__init__(detail)
        self.status = status


class JobNotFound(FalError):
    """fal has no job with this id, or its result has expired."""


@dataclass(frozen=True)
class Image:
    content: bytes
    content_type: str
    url: str


class FalQueue:
    def __init__(self, model: str, key: str) -> None:
        self._model = model
        self._key = key

    def submit(self, arguments: dict[str, Any]) -> str:
        """Queue a job and return fal's request id for it."""
        return self._call("POST", f"{QUEUE_URL}/{self._model}", arguments)["request_id"]

    def is_finished(self, request_id: str) -> bool:
        """Whether the job has stopped running, whether it succeeded or failed."""
        return self._call("GET", f"{self._job_url(request_id)}/status").get("status") == FINISHED

    def image(self, request_id: str) -> Image:
        """The first image of a finished job; a failed job raises FalError with fal's reason."""
        images = self._call("GET", self._job_url(request_id)).get("images") or []
        if not images:
            raise FalError("the job finished without an image")
        return _download(images[0]["url"])

    def _job_url(self, request_id: str) -> str:
        return f"{QUEUE_URL}/{self._model}/requests/{request_id}"

    def _call(self, method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            method=method,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Key {self._key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=CALL_TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = _error_detail(error.read())
            if error.code == 404:
                raise JobNotFound(detail, status=404) from error
            raise FalError(detail, status=error.code) from error
        except urllib.error.URLError as error:
            raise FalError(f"fal could not be reached: {error.reason}") from error


def _download(url: str) -> Image:
    if not url.startswith("https://"):
        raise FalError(f"fal returned an image address that is not https: {url}")
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            return Image(response.read(), response.headers.get_content_type(), url)
    except urllib.error.URLError as error:
        raise FalError(f"the finished image could not be fetched: {error}") from error


def _error_detail(body: bytes) -> str:
    """fal's explanation: a string, or for invalid input a list of {loc, msg} problems."""
    try:
        detail = json.loads(body).get("detail")
    except (ValueError, AttributeError):
        return body.decode("utf-8", "replace")[:500] or "no explanation given"
    if isinstance(detail, list):
        return "; ".join(str(item.get("msg", item)) if isinstance(item, dict) else str(item) for item in detail)
    return str(detail) if detail else "no explanation given"
