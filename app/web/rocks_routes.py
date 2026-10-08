import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Rock, RockStatus, Team, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/rocks")


def _org_rocks_query(org_id: uuid.UUID):
    return (
        select(Rock)
        .join(Team, Rock.team_id == Team.id)
        .where(Team.org_id == org_id)
        .options(joinedload(Rock.owner), joinedload(Rock.team))
        .order_by(Rock.quarter.desc(), Rock.title)
    )


def _current_quarter() -> str:
    today = date.today()
    return f"{today.year}-Q{(today.month - 1) // 3 + 1}"


def _org_teams(db: Session, org_id: uuid.UUID):
    return db.scalars(select(Team).where(Team.org_id == org_id).order_by(Team.name)).all()


def _org_users(db: Session, org_id: uuid.UUID):
    return db.scalars(select(User).where(User.org_id == org_id).order_by(User.name)).all()


def _get_org_rock(db: Session, rock_id: uuid.UUID, org_id: uuid.UUID) -> Rock:
    rock = db.scalar(_org_rocks_query(org_id).where(Rock.id == rock_id))
    if rock is None:
        raise HTTPException(status_code=404)
    return rock


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


def _validate_fields(
    db: Session, org_id: uuid.UUID, team_id: uuid.UUID, owner_id: uuid.UUID, title: str, quarter: str
) -> tuple[str, str]:
    team = db.get(Team, team_id)
    if team is None or team.org_id != org_id:
        raise HTTPException(status_code=404)
    owner = db.get(User, owner_id)
    if owner is None or owner.org_id != org_id:
        raise HTTPException(status_code=404)
    title = title.strip()
    quarter = quarter.strip()
    if not title or len(title) > 255 or not quarter or len(quarter) > 10:
        raise HTTPException(status_code=422)
    return title, quarter


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
):
    rocks = db.scalars(_org_rocks_query(current_user.org_id)).unique().all()
    return templates.TemplateResponse(
        request,
        "rocks/list.html",
        {
            "current_user": current_user,
            "rocks": rocks,
            "teams": _org_teams(db, current_user.org_id),
            "users": _org_users(db, current_user.org_id),
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
):
    _require_admin(current_user)
    title, quarter = _validate_fields(db, current_user.org_id, team_id, owner_id, title, quarter)

    rock = Rock(team_id=team_id, owner_id=owner_id, title=title, quarter=quarter, status=status)
    db.add(rock)
    db.commit()
    return _row_response(request, current_user, _get_org_rock(db, rock.id, current_user.org_id))


@router.get("/{rock_id}")
def get_rock_row(
    request: Request,
    rock_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    return _row_response(request, current_user, _get_org_rock(db, rock_id, current_user.org_id))


@router.get("/{rock_id}/edit")
def edit_rock_row(
    request: Request,
    rock_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    rock = _get_org_rock(db, rock_id, current_user.org_id)
    return templates.TemplateResponse(
        request,
        "rocks/_edit_row.html",
        {
            "current_user": current_user,
            "rock": rock,
            "teams": _org_teams(db, current_user.org_id),
            "users": _org_users(db, current_user.org_id),
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
):
    _require_admin(current_user)
    rock = _get_org_rock(db, rock_id, current_user.org_id)
    title, quarter = _validate_fields(db, current_user.org_id, team_id, owner_id, title, quarter)

    rock.team_id = team_id
    rock.owner_id = owner_id
    rock.title = title
    rock.quarter = quarter
    rock.status = status
    db.commit()
    db.expire_all()
    return _row_response(request, current_user, _get_org_rock(db, rock_id, current_user.org_id))


@router.patch("/{rock_id}/status")
def update_rock_status(
    request: Request,
    rock_id: uuid.UUID,
    status: RockStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    rock = _get_org_rock(db, rock_id, current_user.org_id)

    rock.status = status
    db.commit()
    db.refresh(rock)
    return _row_response(request, current_user, rock)


@router.delete("/{rock_id}")
def delete_rock(
    rock_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    rock = _get_org_rock(db, rock_id, current_user.org_id)
    db.delete(rock)
    db.commit()
    return Response(status_code=200)
