import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.api.scoping import team_ids_for
from app.models.enums import UserRole
from app.models.team import Team
from app.models.user import User
from app.models.vto import VTO
from app.schemas.vto import VTORead, VTOUpsert

router = APIRouter(prefix="/teams/{team_id}/vto", tags=["vto"], dependencies=[Depends(get_current_user)])

write_dep = Depends(require_roles(UserRole.ADMIN, UserRole.MEMBER))
admin_dep = Depends(require_roles(UserRole.ADMIN))


def _get_team_or_404(db: Session, team_id: uuid.UUID, user: User) -> Team:
    # Only the VTO of a team you can work in.
    team = db.get(Team, team_id) if team_id in team_ids_for(db, user) else None
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def _get_vto(db: Session, team_id: uuid.UUID) -> VTO | None:
    return db.scalar(select(VTO).where(VTO.team_id == team_id))


@router.get("", response_model=VTORead)
def get_vto(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_team_or_404(db, team_id, current_user)
    vto = _get_vto(db, team_id)
    if vto is None:
        raise HTTPException(status_code=404, detail="VTO not set for this team yet")
    return vto


@router.put("", response_model=VTORead, dependencies=[write_dep])
def upsert_vto(
    team_id: uuid.UUID,
    payload: VTOUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team = _get_team_or_404(db, team_id, current_user)
    vto = _get_vto(db, team_id)
    if vto is None:
        vto = VTO(org_id=team.org_id, team_id=team.id, **payload.model_dump())
        db.add(vto)
    else:
        for field, value in payload.model_dump().items():
            setattr(vto, field, value)
    db.commit()
    db.refresh(vto)
    return vto


@router.delete("", status_code=204, dependencies=[admin_dep])
def delete_vto(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_team_or_404(db, team_id, current_user)
    vto = _get_vto(db, team_id)
    if vto is None:
        raise HTTPException(status_code=404, detail="VTO not set for this team yet")
    db.delete(vto)
    db.commit()
