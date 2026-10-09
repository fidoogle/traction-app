import json
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.core import meeting_session
from app.models import Meeting, MeetingStatus, User
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
                    },
    )


@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    # Any of the user's teams, not just the current one (see scorecard_routes).
    meeting = db.scalar(_meetings_query(team_ctx.team_ids).where(Meeting.id == meeting_id))
    if meeting is None:
        raise HTTPException(status_code=404)
    team_ctx.require_admin(meeting.team_id)
    if meeting.status == MeetingStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Finish the running meeting first.")
    db.delete(meeting)
    db.commit()
    return Response(status_code=200)


# --- Running a meeting from the sidebar --------------------------------------
# Admins of the team only. Each endpoint answers with the re-rendered sidebar nav (which
# htmx swaps over #site-nav); when a step was started it also asks the browser
# to open that step's page (see static/meeting.js), leaving the rail in place.

def _session_response(
    request: Request,
    db: Session,
    current_user: User,
    meeting,
    go_to_step: int | None = None,
):
    now = meeting_session.now_utc()
    request.state.meeting_session = (
        meeting_session.view(meeting, now) if meeting.status == MeetingStatus.IN_PROGRESS else None
    )
    current_url = request.headers.get("HX-Current-URL", "")
    response = templates.TemplateResponse(
        request,
        "_nav.html",
        {"current_user": current_user, "nav_path": urlparse(current_url).path or "/"},
    )
    if go_to_step is not None:
        response.headers["HX-Trigger"] = json.dumps(
            {"meetingNavigate": meeting_session.step_url(go_to_step)}
        )
    return response


def _admin_session(db: Session, current_user: User, team_ctx: TeamContext):
    """The team's running meeting, for an admin of that team acting on it."""
    if team_ctx.current is None:
        raise HTTPException(status_code=400, detail="Pick a team first.")
    team_ctx.require_admin(team_ctx.current.id)
    meeting = meeting_session.active_meeting(db, team_ctx.current.id)
    if meeting is None:
        raise HTTPException(status_code=409, detail="No meeting is running.")
    return meeting


@router.post("/session/start")
def start_session(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    if team_ctx.current is None:
        raise HTTPException(status_code=400, detail="Pick a team first.")
    team_ctx.require_admin(team_ctx.current.id)
    meeting = meeting_session.start(db, team_ctx.current.id, meeting_session.now_utc())
    db.commit()
    db.refresh(meeting)
    return _session_response(request, db, current_user, meeting, go_to_step=meeting.running_step)


def _step_action(action, request, step, db, current_user, team_ctx):
    meeting = _admin_session(db, current_user, team_ctx)
    try:
        started = action(meeting, step, meeting_session.now_utc())
    except meeting_session.SessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    db.refresh(meeting)
    return _session_response(request, db, current_user, meeting, go_to_step=started)


@router.post("/session/steps/{step}/toggle")
def toggle_step(
    request: Request,
    step: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    def action(meeting, step, now):
        return step if meeting_session.toggle(meeting, step, now) else None

    return _step_action(action, request, step, db, current_user, team_ctx)


@router.post("/session/steps/{step}/stop")
def stop_step(
    request: Request,
    step: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    return _step_action(meeting_session.stop_step, request, step, db, current_user, team_ctx)


@router.post("/session/stop")
def stop_session(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    meeting = _admin_session(db, current_user, team_ctx)
    meeting_session.stop(meeting, meeting_session.now_utc())
    db.commit()
    db.refresh(meeting)
    return _session_response(request, db, current_user, meeting)


@router.post("/session/resume")
def resume_session(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    meeting = _admin_session(db, current_user, team_ctx)
    try:
        step = meeting_session.resume(meeting, meeting_session.now_utc())
    except meeting_session.SessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    db.refresh(meeting)
    return _session_response(request, db, current_user, meeting, go_to_step=step)


@router.post("/session/finish")
def finish_session(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    meeting = _admin_session(db, current_user, team_ctx)
    try:
        meeting_session.finish(meeting, meeting_session.now_utc())
    except meeting_session.SessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    db.refresh(meeting)
    return _session_response(request, db, current_user, meeting)
