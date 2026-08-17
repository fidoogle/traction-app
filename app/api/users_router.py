import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.core.security import hash_password
from app.crud.base import CRUDBase
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(get_current_user)])
crud = CRUDBase(User)

# Fields a non-admin may change on their own account via PATCH.
SELF_SERVICE_FIELDS = {"name", "email", "password"}


@router.post(
    "/",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"password"})
    user = User(**data, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/", response_model=list[UserRead])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_multi(db, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = crud.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = crud.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    is_self = current_user.id == user_id
    if current_user.role != UserRole.ADMIN:
        if not is_self:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        provided_fields = payload.model_dump(exclude_unset=True).keys()
        if provided_fields - SELF_SERVICE_FIELDS:
            raise HTTPException(
                status_code=403,
                detail="Can only update your own name, email, or password",
            )

    update_data = payload.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in update_data.items():
        setattr(user, field, value)
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete(
    "/{user_id}",
    status_code=204,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = crud.remove(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
