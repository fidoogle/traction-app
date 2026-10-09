import uuid
from typing import Generic, Optional, Sequence, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    # `scope` below is a WHERE clause limiting which rows the caller may reach
    # (see app/api/scoping.py); None means unrestricted.

    def get(
        self, db: Session, id: uuid.UUID, scope: Optional[ColumnElement[bool]] = None
    ) -> Optional[ModelType]:
        if scope is None:
            return db.get(self.model, id)
        return db.scalar(select(self.model).where(self.model.id == id, scope))

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        scope: Optional[ColumnElement[bool]] = None,
    ) -> Sequence[ModelType]:
        query = select(self.model)
        if scope is not None:
            query = query.where(scope)
        return db.scalars(query.offset(skip).limit(limit)).all()

    def create(self, db: Session, obj_in: CreateSchemaType) -> ModelType:
        obj = self.model(**obj_in.model_dump())
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db: Session, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType:
        for field, value in obj_in.model_dump(exclude_unset=True).items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(
        self, db: Session, id: uuid.UUID, scope: Optional[ColumnElement[bool]] = None
    ) -> Optional[ModelType]:
        obj = self.get(db, id, scope)
        if obj is not None:
            db.delete(obj)
            db.commit()
        return obj
