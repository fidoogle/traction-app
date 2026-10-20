from enum import StrEnum


class RockStatus(StrEnum):
    ON_TRACK = "on_track"
    OFF_TRACK = "off_track"
    DONE = "done"


class IssueStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DROPPED = "dropped"


class TodoStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    DROPPED = "dropped"


class MeetingStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELED = "canceled"


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class GoalDirection(StrEnum):
    AT_LEAST = "gte"
    AT_MOST = "lte"
    EXACTLY = "eq"


class MeasurableUnit(StrEnum):
    NUMBER = "number"
    CURRENCY = "currency"
    PERCENT = "percent"


# Default list order for anything with a status: still-active items first,
# then finished ones, then dropped. Lower sorts first. Shared by the SQL
# ordering (status_order) and the tables' data-sort values.
STATUS_RANK = {
    "open": 0,
    "on_track": 0,
    "off_track": 0,
    "resolved": 1,
    "done": 1,
    "dropped": 2,
}


def status_rank(status) -> int:
    return STATUS_RANK.get(str(getattr(status, "value", status)), 0)


def status_state(status) -> str:
    """"open", "closed" (resolved/done) or "dropped" - drives a row's look."""
    return ("open", "closed", "dropped")[status_rank(status)]


def status_order(column):
    """SQL ORDER BY expression ranking `column` (an enum status) by STATUS_RANK."""
    from sqlalchemy import case

    enum_class = column.type.enum_class
    return case(
        *[
            (column == enum_class(value), rank)
            for value, rank in STATUS_RANK.items()
            if value in {m.value for m in enum_class}
        ],
        else_=0,
    )
