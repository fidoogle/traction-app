from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Issue, IssueStatus, Meeting, MeetingStatus, Rock, RockStatus, Team
from app.models.user import User
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter()


@router.get("/")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    org_team_ids = select(Team.id).where(Team.org_id == current_user.org_id)

    open_rocks = db.scalar(
        select(func.count())
        .select_from(Rock)
        .where(Rock.team_id.in_(org_team_ids), Rock.status != RockStatus.DONE)
    )
    off_track_rocks = db.scalar(
        select(func.count())
        .select_from(Rock)
        .where(Rock.team_id.in_(org_team_ids), Rock.status == RockStatus.OFF_TRACK)
    )
    open_issues = db.scalar(
        select(func.count())
        .select_from(Issue)
        .where(Issue.team_id.in_(org_team_ids), Issue.status == IssueStatus.OPEN)
    )
    upcoming_meetings = db.scalars(
        select(Meeting)
        .options(joinedload(Meeting.team))
        .where(
            Meeting.team_id.in_(org_team_ids),
            Meeting.status == MeetingStatus.SCHEDULED,
            Meeting.scheduled_date >= date.today(),
        )
        .order_by(Meeting.scheduled_date)
        .limit(5)
    ).all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "current_user": current_user,
            "open_rocks": open_rocks,
            "off_track_rocks": off_track_rocks,
            "open_issues": open_issues,
            "upcoming_meetings": upcoming_meetings,
        },
    )
