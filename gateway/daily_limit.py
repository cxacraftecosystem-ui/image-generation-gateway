"""The daily image allowance, counted in DynamoDB, so an open API still has a ceiling on spending.

Days run on India Standard Time. Counters delete themselves after a week (table TTL).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = ["DailyLimit", "DailyLimitReached"]

IST = timezone(timedelta(hours=5, minutes=30))
COUNTER_LIFETIME = timedelta(days=7)


class DailyLimitReached(Exception):
    """Today's allowance of images has been used."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"Today's {limit} images have been used. The allowance resets at midnight IST.")
        self.limit = limit


class DailyLimit:
    def __init__(self, dynamodb: Any, table: str, *, images_per_day: int) -> None:
        self._dynamodb = dynamodb
        self._table = table
        self._images_per_day = images_per_day

    def take(self, now: datetime) -> None:
        """Count one image against today's allowance, or raise DailyLimitReached."""
        try:
            self._dynamodb.update_item(
                TableName=self._table,
                Key=self._counter(now),
                UpdateExpression="SET expires_at = :expires_at ADD images :one",
                ConditionExpression="attribute_not_exists(images) OR images < :limit",
                ExpressionAttributeValues={
                    ":one": {"N": "1"},
                    ":limit": {"N": str(self._images_per_day)},
                    ":expires_at": {"N": str(int((now + COUNTER_LIFETIME).timestamp()))},
                },
            )
        except self._dynamodb.exceptions.ConditionalCheckFailedException as error:
            raise DailyLimitReached(self._images_per_day) from error

    def give_back(self, now: datetime) -> None:
        """Return an image that was counted but never started, because fal refused the job."""
        self._dynamodb.update_item(
            TableName=self._table,
            Key=self._counter(now),
            UpdateExpression="ADD images :minus_one",
            ExpressionAttributeValues={":minus_one": {"N": "-1"}},
        )

    def _counter(self, now: datetime) -> dict[str, Any]:
        return {"pk": {"S": f"day#{now.astimezone(IST).date().isoformat()}"}}
