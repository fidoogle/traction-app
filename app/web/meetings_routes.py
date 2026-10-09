import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Meeting, MeetingStatus, User, UserRole
from app.web.deps import get_current_user_web, get_team_context
from app.web.team_context import TeamContext
from app.web.templates import templates

router = APIRouter(prefix="/meetings")


def _meetings_query(team_ids: list[uuid.UUID]):
    return (
        select(Meeting)
        .where(Meeting.team_id.in_(team_ids))
        .options(joinedload(Meeting.team))
        .order_by(Meeting.scheduled_date.desc())
    )


@router.get("")
def list_meetings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    meetings = db.scalars(_meetings_query(team_ctx.scope_ids)).unique().all()
    default_team = team_ctx.default_team(current_user.team_id)
    return templates.TemplateResponse(
        request,
        "meetings/list.html",
        {
            "current_user": current_user,
            "meetings": meetings,
            "teams": team_ctx.teams,
            "default_team_id": default_team.id if default_team else None,
            "MeetingStatus": MeetingStatus,
        },
    )


@router.post("")
def create_meeting(
    request: Request,
    team_id: uuid.UUID = Form(...),
    scheduled_date: date = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    team = team_ctx.get_team(team_id)

    meeting = Meeting(team_id=team.id, scheduled_date=scheduled_date)
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return templates.TemplateResponse(
        request,
        "meetings/_row.html",
        {"current_user": current_user, "meeting": meeting, "MeetingStatus": MeetingStatus},
    )


@router.patch("/{meeting_id}/status")
def update_meeting_status(
    request: Request,
    meeting_id: uuid.UUID,
    status: MeetingStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    # Any of the user's teams, not just the current one (see scorecard_routes).
    meeting = db.scalar(_meetings_query(team_ctx.team_ids).where(Meeting.id == meeting_id))
    if meeting is None:
        raise HTTPException(status_code=404)
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)

    meeting.status = status
    db.commit()
    db.refresh(meeting)
    return templates.TemplateResponse(
        request,
        "meetings/_row.html",
        {"current_user": current_user, "meeting": meeting, "MeetingStatus": MeetingStatus},
    )
