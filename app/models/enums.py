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
