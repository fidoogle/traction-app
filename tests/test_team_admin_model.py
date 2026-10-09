import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.team_access import administered_team_ids
from app.db import SessionLocal
from app.models import TeamMembership, User, UserRole
from app.web.team_context import build_team_context


def _flag(db, user_id, team_id, value=True):
    m = db.scalar(
        select(TeamMembership).where(
            TeamMembership.user_id == user_id, TeamMembership.team_id == team_id
        )
    )
    m.is_team_admin = value
    db.commit()


def test_member_administers_only_their_flagged_team(world):
    with SessionLocal() as db:
        _flag(db, world["mia"], world["team_bravo"])
        mia = db.get(User, world["mia"])
        assert administered_team_ids(db, mia) == {world["team_bravo"]}
        ctx = build_team_context(db, mia, None)
        assert ctx.can_admin(world["team_bravo"])
        assert not ctx.can_admin(world["team_alpha"])
        assert not ctx.can_admin(None)


def test_admin_administers_every_team_in_their_org(world):
    with SessionLocal() as db:
        admin = db.get(User, world["admin"])
        assert administered_team_ids(db, admin) == {
            world["team_alpha"], world["team_bravo"], world["team_charlie"],
        }


def test_unflagged_member_and_stale_viewer_flag_get_nothing(world):
    with SessionLocal() as db:
        assert administered_team_ids(db, db.get(User, world["max"])) == set()
        _flag(db, world["vic"], world["team_alpha"])
        vic = db.get(User, world["vic"])
        assert vic.role == UserRole.VIEWER
        assert administered_team_ids(db, vic) == set()


def test_person_can_be_team_admin_of_only_one_team(world):
    with SessionLocal() as db:
        _flag(db, world["mia"], world["team_alpha"])
        with pytest.raises(IntegrityError):
            _flag(db, world["mia"], world["team_bravo"])
