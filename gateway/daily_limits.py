"""Daily image allowances, counted in DynamoDB, so a leaked or over-used key costs a bounded amount.

Each student key may start a set number of images a day, and all keys together a larger
number. Days run on India Standard Time. Counters delete themselves after a week (table TTL).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = ["DailyLimitReached", "DailyLimits"]

IST = timezone(timedelta(hours=5, minutes=30))
COUNTER_LIFETIME = timedelta(days=7)
EVERYONE = "everyone"


class DailyLimitReached(Exception):
    """A key, or all keys together, have used today's allowance."""

    def __init__(self, scope: str, limit: int) -> None:
        whose = "All students together have" if scope == EVERYONE else "This key has"
        super().__init__(f"{whose} used today's {limit} images. The allowance resets at midnight IST.")
        self.scope = scope
        self.limit = limit


class DailyLimits:
    def __init__(self, dynamodb: Any, table: str, *, per_key: int, overall: int) -> None:
        self._dynamodb = dynamodb
        self._table = table
        self._limits = {"key": per_key, EVERYONE: overall}

    def take(self, key_id: str, now: datetime) -> None:
        """Count one image against the key and against everyone, or raise DailyLimitReached."""
        counters = self._counters(key_id, now)
        try:
            self._dynamodb.transact_write_items(
                TransactItems=[self._increment(pk, scope, now) for scope, pk in counters]
            )
        except self._dynamodb.exceptions.TransactionCanceledException as error:
            reasons = error.response.get("CancellationReasons", [])
            for (scope, _), reason in zip(counters, reasons):
                if reason.get("Code") == "ConditionalCheckFailed":
                    raise DailyLimitReached(scope, self._limits[scope]) from error
            raise

    def give_back(self, key_id: str, now: datetime) -> None:
        """Return an image that was counted but never started, because fal refused the job."""
        for _, pk in self._counters(key_id, now):
            self._dynamodb.update_item(
                TableName=self._table,
                Key={"pk": {"S": pk}},
                UpdateExpression="ADD images :minus_one",
                ExpressionAttributeValues={":minus_one": {"N": "-1"}},
            )

    def _counters(self, key_id: str, now: datetime) -> list[tuple[str, str]]:
        day = now.astimezone(IST).date().isoformat()
        return [("key", f"key#{key_id}#{day}"), (EVERYONE, f"{EVERYONE}#{day}")]

    def _increment(self, pk: str, scope: str, now: datetime) -> dict[str, Any]:
        return {
            "Update": {
                "TableName": self._table,
                "Key": {"pk": {"S": pk}},
                "UpdateExpression": "SET expires_at = :expires_at ADD images :one",
                "ConditionExpression": "attribute_not_exists(images) OR images < :limit",
                "ExpressionAttributeValues": {
                    ":one": {"N": "1"},
                    ":limit": {"N": str(self._limits[scope])},
                    ":expires_at": {"N": str(int((now + COUNTER_LIFETIME).timestamp()))},
                },
            }
        }
