from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core import activity

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Writes an ActivityLog entry for every add/edit/delete made by a signed-in user.
activity.register(SessionLocal)
