"""Lambda entry point behind API Gateway: the two routes students' pages call.

    POST /                  start an image; returns {"call_id", "status": "queued"}
    GET  /result/{call_id}  202 {"status": "processing"} until done, then the image itself

Same routes and replies as the Modal app this replaces, so pages only change the base URL.
Like that app, the API is open (no key); the daily image limit caps spending.
"""

import base64
import json
import logging
import re
from datetime import datetime, timezone
from functools import cache
from typing import Any

import boto3

from gateway.daily_limit import DailyLimit, DailyLimitReached
from gateway.fal_queue import FalError, FalQueue, JobNotFound
from gateway.generation import FAL_MODEL, InvalidRequest, fal_arguments, parse_request
from gateway.settings import Settings, load_settings

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CALL_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Expose-Headers": "X-Image-Url",
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    route = (event.get("httpMethod"), event.get("resource"))
    if route == ("POST", "/"):
        return _start(event)
    if route == ("GET", "/result/{call_id}"):
        return _result(event)
    return _json(404, {"error": "no such route"})


def _start(event: dict[str, Any]) -> dict[str, Any]:
    settings, queue, limit = _services()
    try:
        request = parse_request(_body(event), settings.styles.keys())
    except InvalidRequest as error:
        return _json(400, {"error": str(error)})
    now = datetime.now(timezone.utc)
    try:
        limit.take(now)
    except DailyLimitReached as error:
        return _json(429, {"error": str(error)})
    try:
        call_id = queue.submit(fal_arguments(request, settings.styles[request.style]))
    except FalError as error:
        limit.give_back(now)
        logger.error("fal refused a job: %s", error)
        return _json(502, {"error": f"the image service refused the job: {error}"})
    logger.info("queued %s: %s %dx%d", call_id, request.style, request.width, request.height)
    return _json(200, {"call_id": call_id, "status": "queued"})


def _result(event: dict[str, Any]) -> dict[str, Any]:
    call_id = (event.get("pathParameters") or {}).get("call_id", "")
    if not CALL_ID.match(call_id):
        return _json(400, {"error": "call_id is not one this API gave out"})
    _, queue, _ = _services()
    try:
        if not queue.is_finished(call_id):
            return _json(202, {"status": "processing"})
        image = queue.image(call_id)
    except JobNotFound:
        return _json(404, {"error": "No such job, or its result has expired"})
    except FalError as error:
        logger.warning("job %s failed: %s", call_id, error)
        return _json(500, {"status": "failed", "error": str(error)})
    return {
        "statusCode": 200,
        "isBase64Encoded": True,
        "headers": {**CORS_HEADERS, "Content-Type": image.content_type, "X-Image-Url": image.url},
        "body": base64.b64encode(image.content).decode("ascii"),
    }


def _body(event: dict[str, Any]) -> Any:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        return json.loads(raw)
    except ValueError as error:
        raise InvalidRequest("body must be JSON") from error


# Exception to "no module-level state": Lambda reuses a warm container, so the settings,
# the fal key from Secrets Manager and the AWS clients are built once per container.
@cache
def _services() -> tuple[Settings, FalQueue, DailyLimit]:
    settings = load_settings()
    fal_key = boto3.client("secretsmanager").get_secret_value(SecretId=settings.fal_key_secret_id)["SecretString"]
    limit = DailyLimit(boto3.client("dynamodb"), settings.usage_table, images_per_day=settings.images_per_day)
    return settings, FalQueue(FAL_MODEL, fal_key), limit


def _json(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(payload),
    }
