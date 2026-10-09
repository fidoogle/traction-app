import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Rock, RockStatus, Team, User, UserRole
from app.web.deps import get_current_user_web, get_team_context
from app.web.notes import clean_notes, notes_form_response
from app.web.team_context import TeamContext, require_member, team_people
from app.web.templates import templates

router = APIRouter(prefix="/rocks")


def _rocks_query(team_ids: list[uuid.UUID]):
    return (
        select(Rock)
        .where(Rock.team_id.in_(team_ids))
        .options(joinedload(Rock.owner), joinedload(Rock.team))
        .order_by(Rock.quarter.desc(), Rock.title)
    )


def _current_quarter() -> str:
    today = date.today()
    return f"{today.year}-Q{(today.month - 1) // 3 + 1}"


def _get_rock(db: Session, rock_id: uuid.UUID, team_ctx: TeamContext) -> Rock:
    # Any of the user's teams, not just the current one (see scorecard_routes).
    rock = db.scalar(_rocks_query(team_ctx.team_ids).where(Rock.id == rock_id))
    if rock is None:
        raise HTTPException(status_code=404)
    return rock


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


def _validate_fields(
    team_ctx: TeamContext,
    team_id: uuid.UUID,
    owner_id: uuid.UUID,
    title: str,
    quarter: str,
    keep_owner: uuid.UUID | None = None,
) -> tuple[Team, str, str]:
    team = team_ctx.get_team(team_id)
    require_member(team, owner_id, keep=keep_owner)
    title = title.strip()
    quarter = quarter.strip()
    if not title or len(title) > 255 or not quarter or len(quarter) > 10:
        raise HTTPException(status_code=422)
    return team, title, quarter


def _row_response(request: Request, current_user: User, rock: Rock):
    return templates.TemplateResponse(
        request,
        "rocks/_row.html",
        {"current_user": current_user, "rock": rock, "RockStatus": RockStatus},
    )


@router.get("")
def list_rocks(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    rocks = db.scalars(_rocks_query(team_ctx.scope_ids)).unique().all()
    default_team = team_ctx.default_team(current_user.team_id)
    return templates.TemplateResponse(
        request,
        "rocks/list.html",
        {
            "current_user": current_user,
            "rocks": rocks,
            "teams": team_ctx.teams,
            "default_team_id": default_team.id if default_team else None,
            "users": team_people(db, team_ctx),
            "default_quarter": _current_quarter(),
            "RockStatus": RockStatus,
        },
    )


@router.post("")
def create_rock(
    request: Request,
    team_id: uuid.UUID = Form(...),
    owner_id: uuid.UUID = Form(...),
    title: str = Form(...),
    quarter: str = Form(...),
    status: RockStatus = Form(RockStatus.ON_TRACK),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    _require_admin(current_user)
    team, title, quarter = _validate_fields(team_ctx, team_id, owner_id, title, quarter)

    rock = Rock(team_id=team.id, owner_id=owner_id, title=title, quarter=quarter, status=status)
    db.add(rock)
    db.commit()
    return _row_response(request, current_user, _get_rock(db, rock.id, team_ctx))


@router.get("/{rock_id}")
def get_rock_row(
    request: Request,
    rock_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    return _row_response(request, current_user, _get_rock(db, rock_id, team_ctx))


@router.get("/{rock_id}/edit")
def edit_rock_row(
    request: Request,
    rock_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    _require_admin(current_user)
    rock = _get_rock(db, rock_id, team_ctx)
    return templates.TemplateResponse(
        request,
        "rocks/_edit_row.html",
        {
            "current_user": current_user,
            "rock": rock,
            "teams": team_ctx.teams,
            "users": team_people(db, team_ctx, keep_ids=[rock.owner_id]),
            "RockStatus": RockStatus,
        },
    )


@router.put("/{rock_id}")
def update_rock(
    request: Request,
    rock_id: uuid.UUID,
    team_id: uuid.UUID = Form(...),
    owner_id: uuid.UUID = Form(...),
    title: str = Form(...),
    quarter: str = Form(...),
    status: RockStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    _require_admin(current_user)
    rock = _get_rock(db, rock_id, team_ctx)
    # The owner may stay even if they've left the rock's team - but not when
    # moving the rock to another team, where they must be a member.
    team, title, quarter = _validate_fields(
        team_ctx,
        team_id,
        owner_id,
        title,
        quarter,
        keep_owner=rock.owner_id if team_id == rock.team_id else None,
    )

    rock.team_id = team.id
    rock.owner_id = owner_id
    rock.title = title
    rock.quarter = quarter
    rock.status = status
    db.commit()
    db.expire_all()
    return _row_response(request, current_user, _get_rock(db, rock_id, team_ctx))


@router.patch("/{rock_id}/status")
def update_rock_status(
    request: Request,
    rock_id: uuid.UUID,
    status: RockStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    _require_admin(current_user)
    rock = _get_rock(db, rock_id, team_ctx)

    rock.status = status
    db.commit()
    db.refresh(rock)
    return _row_response(request, current_user, rock)


@router.delete("/{rock_id}")
def delete_rock(
    rock_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    _require_admin(current_user)
    rock = _get_rock(db, rock_id, team_ctx)
    db.delete(rock)
    db.commit()
    return Response(status_code=200)


@router.get("/{rock_id}/notes")
def get_rock_notes(
    request: Request,
    rock_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    rock = _get_rock(db, rock_id, team_ctx)
    return notes_form_response(
        request,
        subject=rock.title,
        url=f"/rocks/{rock.id}/notes",
        row_id=f"rock-row-{rock.id}",
        notes=rock.notes,
        can_edit=current_user.role == UserRole.ADMIN,
    )


@router.put("/{rock_id}/notes")
def update_rock_notes(
    request: Request,
    rock_id: uuid.UUID,
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    _require_admin(current_user)
    rock = _get_rock(db, rock_id, team_ctx)
    rock.notes = clean_notes(notes)
    db.commit()
    db.expire_all()
    return _row_response(request, current_user, _get_rock(db, rock_id, team_ctx))
