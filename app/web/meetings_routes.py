import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Meeting, MeetingStatus, Team, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/meetings")


def _org_meetings_query(org_id: uuid.UUID):
    return (
        select(Meeting)
        .join(Team, Meeting.team_id == Team.id)
        .where(Team.org_id == org_id)
        .options(joinedload(Meeting.team))
        .order_by(Meeting.scheduled_date.desc())
    )


@router.get("")
def list_meetings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    meetings = db.scalars(_org_meetings_query(current_user.org_id)).unique().all()
    teams = db.scalars(
        select(Team).where(Team.org_id == current_user.org_id).order_by(Team.name)
    ).all()
    return templates.TemplateResponse(
        request,
        "meetings/list.html",
        {
            "current_user": current_user,
            "meetings": meetings,
            "teams": teams,
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
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    team = db.get(Team, team_id)
    if team is None or team.org_id != current_user.org_id:
        raise HTTPException(status_code=404)

    meeting = Meeting(team_id=team_id, scheduled_date=scheduled_date)
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
):
    meeting = db.scalar(
        select(Meeting)
        .join(Team, Meeting.team_id == Team.id)
        .where(Meeting.id == meeting_id, Team.org_id == current_user.org_id)
        .options(joinedload(Meeting.team))
    )
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
