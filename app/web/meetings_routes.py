import json
import uuid
from datetime import date, time
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.config import settings
from app.core import ical, meeting_session
from app.core.meeting_emails import calendar_file, send_meeting_cancelled, send_meeting_invites
from app.core.org_time import local_to_utc, tz_of
from app.models import Meeting, MeetingStatus, Todo, TodoStatus, User
from app.web.deps import get_current_user_web, get_team_context
from app.web.team_context import TeamContext
from app.web.templates import templates

router = APIRouter(prefix="/meetings")


def _meetings_query(team_ids: list[uuid.UUID]):
    return (
        select(Meeting)
        .where(Meeting.team_id.in_(team_ids))
        .options(joinedload(Meeting.team))
        .order_by(Meeting.scheduled_start.desc())
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
            "admin_teams": team_ctx.admin_teams,
            "tz": tz_of(current_user.organization.timezone),
        },
    )


MIN_MINUTES, MAX_MINUTES = 15, 480


def _slot(day: date, at: time, duration_minutes: int, location: str, user: User):
    """(start in UTC, length, location) from the form, which is in the organization's zone."""
    if not MIN_MINUTES <= duration_minutes <= MAX_MINUTES:
        raise HTTPException(status_code=422, detail="A meeting runs 15 minutes to 8 hours.")
    location = location.strip()
    if len(location) > 255 or "\n" in location or "\r" in location:
        raise HTTPException(status_code=422, detail="Location must be one short line.")
    start = local_to_utc(day, at, tz_of(user.organization.timezone))
    return start, duration_minutes, location or None


def _get_meeting(db: Session, meeting_id: uuid.UUID, team_ctx: TeamContext) -> Meeting:
    meeting = db.scalar(_meetings_query(team_ctx.team_ids).where(Meeting.id == meeting_id))
    if meeting is None:
        raise HTTPException(status_code=404)
    return meeting


def _row_response(request: Request, current_user: User, meeting: Meeting, template: str = "meetings/_row.html"):
    return templates.TemplateResponse(
        request,
        template,
        {
            "current_user": current_user,
            "meeting": meeting,
            "tz": tz_of(current_user.organization.timezone),
        },
    )


@router.post("")
def create_meeting(
    request: Request,
    background_tasks: BackgroundTasks,
    team_id: uuid.UUID = Form(...),
    day: date = Form(...),
    at: time = Form(...),
    duration_minutes: int = Form(90),
    location: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    team_ctx.require_admin(team_id)
    team = team_ctx.get_team(team_id)
    start, minutes, where = _slot(day, at, duration_minutes, location, current_user)
    if start <= meeting_session.now_utc():
        raise HTTPException(status_code=422, detail="Pick a time in the future.")
    meeting = Meeting(team_id=team.id, scheduled_start=start, duration_minutes=minutes, location=where)
    db.add(meeting)
    db.commit()
    if settings.email_enabled:
        background_tasks.add_task(send_meeting_invites, meeting.id, meeting.ical_sequence)
    return _row_response(request, current_user, _get_meeting(db, meeting.id, team_ctx))


@router.get("/{meeting_id}")
def get_meeting_row(
    request: Request,
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    return _row_response(request, current_user, _get_meeting(db, meeting_id, team_ctx))


@router.get("/{meeting_id}/edit")
def edit_meeting_row(
    request: Request,
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    meeting = _get_meeting(db, meeting_id, team_ctx)
    team_ctx.require_admin(meeting.team_id)
    if meeting.status != MeetingStatus.SCHEDULED:
        raise HTTPException(status_code=409, detail="Only a scheduled meeting can be changed.")
    return _row_response(request, current_user, meeting, "meetings/_edit_row.html")


@router.put("/{meeting_id}")
def update_meeting(
    request: Request,
    background_tasks: BackgroundTasks,
    meeting_id: uuid.UUID,
    day: date = Form(...),
    at: time = Form(...),
    duration_minutes: int = Form(90),
    location: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    meeting = _get_meeting(db, meeting_id, team_ctx)
    team_ctx.require_admin(meeting.team_id)
    if meeting.status != MeetingStatus.SCHEDULED:
        raise HTTPException(status_code=409, detail="Only a scheduled meeting can be changed.")
    start, minutes, where = _slot(day, at, duration_minutes, location, current_user)
    changed = (start, minutes, where) != (meeting.scheduled_start, meeting.duration_minutes, meeting.location)
    if changed:
        if start <= meeting_session.now_utc():
            raise HTTPException(status_code=422, detail="Pick a time in the future.")
        meeting.scheduled_start, meeting.duration_minutes, meeting.location = start, minutes, where
        # Calendars treat a higher SEQUENCE on the same UID as "this replaces what you have".
        meeting.ical_sequence += 1
    db.commit()
    if changed and settings.email_enabled:
        background_tasks.add_task(send_meeting_invites, meeting_id, meeting.ical_sequence)
    db.expire_all()
    return _row_response(request, current_user, _get_meeting(db, meeting_id, team_ctx))


@router.post("/{meeting_id}/cancel")
def cancel_meeting(
    request: Request,
    background_tasks: BackgroundTasks,
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    meeting = _get_meeting(db, meeting_id, team_ctx)
    team_ctx.require_admin(meeting.team_id)
    if meeting.status != MeetingStatus.SCHEDULED:
        raise HTTPException(status_code=409, detail="Only a scheduled meeting can be cancelled.")
    meeting.status = MeetingStatus.CANCELED
    meeting.ical_sequence += 1
    db.commit()
    if settings.email_enabled:
        background_tasks.add_task(send_meeting_cancelled, meeting_id, meeting.ical_sequence)
    db.expire_all()
    return _row_response(request, current_user, _get_meeting(db, meeting_id, team_ctx))


@router.get("/{meeting_id}/calendar.ics")
def meeting_calendar_file(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    """The meeting as a calendar event to add to your own calendar."""
    meeting = _get_meeting(db, meeting_id, team_ctx)
    method = ical.CANCEL if meeting.status == MeetingStatus.CANCELED else ical.PUBLISH
    return Response(
        calendar_file(meeting, meeting.team, method),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="meeting.ics"'},
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


@router.get("/session/finish-recap")
def finish_recap(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    """The modal shown before Finish: the team's still-open to-dos, as a last check."""
    meeting = _admin_session(db, current_user, team_ctx)
    todos = db.scalars(
        select(Todo)
        .where(Todo.team_id == meeting.team_id, Todo.status == TodoStatus.OPEN)
        .options(joinedload(Todo.owner))
        .order_by(Todo.due_date.is_(None), Todo.due_date, Todo.title)
    ).unique().all()
    return templates.TemplateResponse(
        request, "meetings/_finish_recap.html", {"current_user": current_user, "todos": todos}
    )


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
