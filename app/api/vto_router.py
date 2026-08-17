import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.models.enums import UserRole
from app.models.organization import Organization
from app.models.vto import VTO
from app.schemas.vto import VTORead, VTOUpsert

router = APIRouter(
    prefix="/organizations/{org_id}/vto", tags=["vto"], dependencies=[Depends(get_current_user)]
)

write_dep = Depends(require_roles(UserRole.ADMIN, UserRole.MEMBER))
admin_dep = Depends(require_roles(UserRole.ADMIN))


def _get_org_or_404(db: Session, org_id: uuid.UUID) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _get_vto(db: Session, org_id: uuid.UUID) -> VTO | None:
    return db.scalar(select(VTO).where(VTO.org_id == org_id))


@router.get("", response_model=VTORead)
def get_vto(org_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_org_or_404(db, org_id)
    vto = _get_vto(db, org_id)
    if vto is None:
        raise HTTPException(status_code=404, detail="VTO not set for this organization yet")
    return vto


@router.put("", response_model=VTORead, dependencies=[write_dep])
def upsert_vto(org_id: uuid.UUID, payload: VTOUpsert, db: Session = Depends(get_db)):
    _get_org_or_404(db, org_id)
    vto = _get_vto(db, org_id)
    if vto is None:
        vto = VTO(org_id=org_id, **payload.model_dump())
        db.add(vto)
    else:
        for field, value in payload.model_dump().items():
            setattr(vto, field, value)
    db.commit()
    db.refresh(vto)
    return vto


@router.delete("", status_code=204, dependencies=[admin_dep])
def delete_vto(org_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_org_or_404(db, org_id)
    vto = _get_vto(db, org_id)
    if vto is None:
        raise HTTPException(status_code=404, detail="VTO not set for this organization yet")
    db.delete(vto)
    db.commit()
