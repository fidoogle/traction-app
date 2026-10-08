import uuid
from typing import Type

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.crud.base import CRUDBase
from app.models.base import Base
from app.models.enums import UserRole

DEFAULT_WRITE_ROLES = frozenset({UserRole.ADMIN, UserRole.MEMBER})


def build_crud_router(
    *,
    model: Type[Base],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    read_schema: Type[BaseModel],
    prefix: str,
    tags: list[str],
    write_roles: frozenset[UserRole] = DEFAULT_WRITE_ROLES,
    edit_roles: frozenset[UserRole] | None = None,
) -> APIRouter:
    # Router-level dependency requires any authenticated user (covers reads).
    # Creating requires membership in write_roles; updating/deleting requires
    # edit_roles, which defaults to write_roles (so e.g. members can add an
    # item but only admins can change or remove it).
    router = APIRouter(prefix=prefix, tags=tags, dependencies=[Depends(get_current_user)])
    crud = CRUDBase(model)
    not_found_detail = f"{model.__name__} not found"
    write_dep = Depends(require_roles(*write_roles))
    edit_dep = Depends(require_roles(*(edit_roles or write_roles)))

    @router.post("/", response_model=read_schema, status_code=201, dependencies=[write_dep])
    def create_item(payload: create_schema, db: Session = Depends(get_db)):
        return crud.create(db, payload)

    @router.get("/", response_model=list[read_schema])
    def list_items(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        return crud.get_multi(db, skip=skip, limit=limit)

    @router.get("/{item_id}", response_model=read_schema)
    def get_item(item_id: uuid.UUID, db: Session = Depends(get_db)):
        obj = crud.get(db, item_id)
        if obj is None:
            raise HTTPException(status_code=404, detail=not_found_detail)
        return obj

    @router.patch("/{item_id}", response_model=read_schema, dependencies=[edit_dep])
    def update_item(item_id: uuid.UUID, payload: update_schema, db: Session = Depends(get_db)):
        obj = crud.get(db, item_id)
        if obj is None:
            raise HTTPException(status_code=404, detail=not_found_detail)
        return crud.update(db, obj, payload)

    @router.delete("/{item_id}", status_code=204, dependencies=[edit_dep])
    def delete_item(item_id: uuid.UUID, db: Session = Depends(get_db)):
        obj = crud.remove(db, item_id)
        if obj is None:
            raise HTTPException(status_code=404, detail=not_found_detail)

    return router
