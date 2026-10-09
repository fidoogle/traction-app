import uuid

from app.models import Team
from app.web.team_context import ALL_TEAMS, TeamContext, resolve_current_team


def _team(name: str) -> Team:
    return Team(id=uuid.uuid4(), name=name)


LEADERSHIP = _team("Leadership")
OPS = _team("Operations")
OTHER = _team("Someone else's team")
MINE = [LEADERSHIP, OPS]


def test_member_gets_requested_team_they_belong_to():
    assert resolve_current_team(MINE, False, LEADERSHIP.id, str(OPS.id)) is OPS


def test_member_cannot_pick_a_team_they_are_not_on():
    assert resolve_current_team(MINE, False, LEADERSHIP.id, str(OTHER.id)) is LEADERSHIP


def test_member_cannot_pick_all_teams():
    assert resolve_current_team(MINE, False, OPS.id, ALL_TEAMS) is OPS


def test_member_defaults_to_home_team():
    assert resolve_current_team(MINE, False, OPS.id, None) is OPS


def test_member_falls_back_to_first_team_when_home_team_is_gone():
    assert resolve_current_team(MINE, False, OTHER.id, "garbage") is LEADERSHIP


def test_member_with_no_teams_has_no_current_team():
    assert resolve_current_team([], False, None, None) is None


def test_admin_defaults_to_all_teams():
    assert resolve_current_team(MINE, True, LEADERSHIP.id, None) is None


def test_admin_can_pick_a_team_or_all():
    assert resolve_current_team(MINE, True, LEADERSHIP.id, str(OPS.id)) is OPS
    assert resolve_current_team(MINE, True, LEADERSHIP.id, ALL_TEAMS) is None


def test_scope_ids_is_current_team_or_every_team():
    assert TeamContext(teams=MINE, current=OPS).scope_ids == [OPS.id]
    assert TeamContext(teams=MINE, current=None).scope_ids == [LEADERSHIP.id, OPS.id]
    assert TeamContext(teams=[], current=None).scope_ids == []
