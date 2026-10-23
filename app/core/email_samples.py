"""Made-up data for every email, so each one can be rendered on its own: by the
tests (which check they all render cleanly and load nothing from outside) and by
scripts/preview_emails.py (to look at them, or send them to yourself to see how
Outlook, Gmail or a plain-text client shows them).

Add an entry here when you add an email template; a test fails until you do.
"""

from app.core.digest import Digest, TeamSummary

LINK = "https://traction.example.org/rocks"
PREFERENCES = "https://traction.example.org/notifications"

_BASE = {"name": "Mia Member", "base_url": "https://traction.example.org"}

_DIGEST = Digest(
    todos=[
        {"title": "Order the buses", "team": "Operations", "when": "overdue by 2 days", "overdue": True},
        {"title": "Draft the safety plan", "team": "Operations", "when": "due Friday, October 30", "overdue": False},
        {"title": "Call the vendor", "team": "Operations", "when": "no due date", "overdue": False},
    ],
    todos_more=4,
    rocks=[{"title": "Raise reading scores", "team": "Operations"}],
    off_goal=[{"name": "Attendance rate", "actual": "91%", "goal": "≥ 95%"}],
    teams=[
        TeamSummary(
            name="Operations", rocks_total=4, rocks_done=1, rocks_off_track=["Raise reading scores"],
            open_todos=9, overdue_todos=2, open_issues=5, measured=6, off_goal=["Attendance rate"],
        )
    ],
)

SAMPLES: dict[str, dict] = {
    "test": {},
    "welcome": {
        "link": "https://traction.example.org/set-password/abc", "invited_by": "Ada Admin",
        "email": "mia@example.org", "hours": 48, "always_on": True,
    },
    "password_reset": {"link": "https://traction.example.org/set-password/abc", "hours": 1, "always_on": True},
    "todo_assigned": {
        "title": "Order the buses", "team": "Operations", "due": "Tuesday, November 3",
        "assigned_by": "Ada Admin", "link": LINK,
    },
    "rock_assigned": {
        "title": "Raise reading scores", "team": "Operations", "quarter": "2026-Q4",
        "assigned_by": "Ada Admin", "link": LINK,
    },
    "todo_due": {
        "items": [
            {"title": "Order the buses", "team": "Operations", "when": "overdue by 3 days", "overdue": True},
            {"title": "Draft the safety plan", "team": "Operations", "when": "due tomorrow", "overdue": False},
        ],
        "more": 3, "count": 5, "link": LINK,
    },
    "meeting_invite": {
        "team": "Operations", "when": "Tuesday, October 27, 2026, 3:30 PM - 5:00 PM CDT", "location": "Room 4",
        "link": LINK, "updated": False,
        "google_url": "https://calendar.google.com/calendar/render?action=TEMPLATE&text=x",
        "outlook_url": "https://outlook.office.com/calendar/0/deeplink/compose?subject=x",
    },
    "meeting_cancelled": {
        "team": "Operations", "when": "Tuesday, October 27, 2026, 3:30 PM - 5:00 PM CDT", "location": "Room 4", "link": LINK,
    },
    "meeting_reminder": {
        "team": "Operations", "when": "Tuesday, October 27, 2026, 3:30 PM - 5:00 PM CDT", "location": "Room 4",
        "link": LINK, "lead": "tomorrow",
    },
    "weekly_digest": {
        "digest": _DIGEST, "link": "https://traction.example.org/", "todos_link": "https://traction.example.org/todos",
        "rocks_link": LINK, "scorecards_link": "https://traction.example.org/scorecards",
    },
    "rock_off_track": {
        "title": "Raise reading scores", "team": "Operations", "quarter": "2026-Q4", "owner": "Mia Member",
        "changed_by": "Ada Admin", "link": LINK,
    },
    "scorecard_missed": {
        "measure": "Attendance rate", "team": "Operations", "owner": "Mia Member", "goal": "≥ 95%", "streak": 2,
        "results": [{"week": "Week of Oct 12", "actual": "91%"}, {"week": "Week of Oct 19", "actual": "92%"}],
        "link": "https://traction.example.org/scorecards",
    },
    "issue_added": {
        "team": "Operations", "count": 3, "issues": ["Bus route 12 is late", "Heater broken", "Wi-Fi drops"],
        "more": 0, "link": "https://traction.example.org/issues",
    },
    "meeting_summary": {
        "team": "Operations", "when": "Tue, Oct 27, 2026, 3:30 PM", "total": "1:32:10",
        "steps": [
            {"label": "Segue", "time": "5:10", "over": True}, {"label": "Rocks", "time": "4:00", "over": False},
            {"label": "Issues", "time": "58:00", "over": False},
        ],
        "todos": [{"title": "Order the buses", "owner": "Vic Viewer", "due": "Nov 3"}], "todos_more": 0,
        "issues": ["Heater broken"], "issues_more": 0, "issue_count": 1, "link": "https://traction.example.org/meetings",
    },
    "quarter_reminder": {
        "kind": "end", "team": "Operations", "quarter": "2026-Q4", "ends": "December 31",
        "rocks_total": 4, "rocks_done": 1, "unfinished": ["Raise reading scores", "Hire a counselor"], "link": LINK,
    },
    "admin_system": {
        "headline": "Email delivery problems: 6 failed in the last day",
        "lines": ["6 emails could not be sent in the last 24 hours.", "Most recent error: Connection refused"],
        "link": "https://traction.example.org/users",
    },
}


def context_for(template: str) -> dict:
    """The sample data for a template, including the name and the footer link
    (account emails get the 'cannot be turned off' note instead)."""
    context = {**_BASE, **SAMPLES[template]}
    if not context.get("always_on"):
        context["preferences_url"] = PREFERENCES
    return context
