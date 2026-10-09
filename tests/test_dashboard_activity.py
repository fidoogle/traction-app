"""The Dashboard and the Activity feed follow the current team."""

import re

from conftest import titles


def stats(browser) -> dict[str, int]:
    html = browser.get("/").text
    pairs = re.findall(r'<div class="value">(\d+)</div>\s*<div class="label">([^<]+)</div>', html)
    return {label: int(value) for value, label in pairs}


def meeting_teams(browser) -> set[str]:
    html = browser.get("/").text
    return set(re.findall(r"<td>(Alpha|Bravo|Charlie|Xray)</td>", html))


def test_dashboard_counts_the_current_team_only(world, login):
    mia = login("mia")  # Alpha + Bravo, one open rock and issue on each
    assert stats(mia) == {"Open rocks": 1, "Off-track rocks": 0, "Open issues": 1}
    assert meeting_teams(mia) == {"Alpha"}
    mia.switch_team(world["team_bravo"])
    assert meeting_teams(mia) == {"Bravo"}
    assert "Bravo" in mia.get("/").text.split("Showing", 1)[1].split("</p>")[0]


def test_dashboard_for_an_admin_covers_their_whole_org_and_nothing_else(world, login):
    admin = login("admin")
    assert stats(admin)["Open rocks"] == 3  # Alpha, Bravo, Charlie - not the other org's
    assert meeting_teams(admin) == {"Alpha", "Bravo", "Charlie"}
    admin.switch_team(world["team_charlie"])
    assert stats(admin)["Open rocks"] == 1


def test_a_member_cannot_widen_the_dashboard_with_a_forged_cookie(world, login):
    max_ = login("max")  # Charlie only
    max_.client.cookies.set("current_team", "all")
    assert meeting_teams(max_) == {"Charlie"}


# --- Activity ---------------------------------------------------------------


def make_news(world, login):
    """Admin adds a rock to Alpha and to Charlie, and creates a user (org-level)."""
    admin = login("admin")
    rock = {"quarter": "2026-Q4"}
    admin.post("/rocks", data={**rock, "title": "News on alpha", "team_id": str(world["team_alpha"]),
                               "owner_id": str(world["mia"])})
    admin.post("/rocks", data={**rock, "title": "News on charlie", "team_id": str(world["team_charlie"]),
                               "owner_id": str(world["max"])})
    admin.post("/users", data={"name": "Newcomer", "email": "new@example.com", "role": "member",
                               "password": "long-enough-pw", "team_ids": str(world["team_alpha"])})
    return admin


def feed(browser) -> str:
    return browser.get("/activity").text


def test_feed_shows_only_the_current_teams_activity(world, login):
    make_news(world, login)
    mia = login("mia")
    html = feed(mia)
    assert "News on alpha" in html
    assert "News on charlie" not in html
    assert "Newcomer" not in html  # user changes are admin-only
    mia.switch_team(world["team_bravo"])
    assert "News on alpha" not in feed(mia)
    assert "News on charlie" in feed(login("max"))


def test_admin_feed_follows_the_current_team_and_all_teams_includes_org_changes(world, login):
    admin = make_news(world, login)
    html = feed(admin)  # All teams
    assert "News on alpha" in html and "News on charlie" in html and "Newcomer" in html
    admin.switch_team(world["team_charlie"])
    html = feed(admin)
    assert "News on charlie" in html
    assert "News on alpha" not in html and "Newcomer" not in html


def test_activity_stays_inside_the_org(world, login):
    make_news(world, login)
    assert "News on" not in feed(login("other"))


def test_unread_badge_only_counts_what_you_can_see(world, login):
    make_news(world, login)

    def unread(browser) -> int:
        html = browser.get("/activity/badge").text
        match = re.search(r'has-unread[^>]*>\s*(\d+)', html)
        return int(match.group(1)) if match else 0

    assert unread(login("mia")) == 1  # the Alpha rock; not Charlie's, not the new user
    assert unread(login("max")) == 1  # the Charlie rock
    assert unread(login("admin")) == 0  # their own changes aren't news to them


def test_older_entries_page_is_scoped_too(world, login):
    make_news(world, login)
    mia = login("mia")
    html = mia.get("/activity/entries", params={"before": 10**9, "last_seen": "2000-01-01T00:00:00Z"}).text
    assert "News on alpha" in html
    assert "News on charlie" not in html
    assert titles(html, "rock") == set()  # (seed items weren't logged: no actor then)
