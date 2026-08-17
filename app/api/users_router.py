import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import hash_password
from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(get_current_user)])
crud = CRUDBase(User)


@router.post("/", response_model=UserRead, status_code=201)
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
def update_user(user_id: uuid.UUID, payload: UserUpdate, db: Session = Depends(get_db)):
    user = crud.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = payload.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in update_data.items():
        setattr(user, field, value)
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = crud.remove(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
