# Future Enhancements

Backlog of features and improvements identified while building the app.
Check items off as they're implemented; add new ones as they come up.
When picking up new work, skim this file first — mark anything that's
already done, and consider suggesting the next item if nothing else is
queued.

## Authorization & Access Control

- [ ] Refresh tokens / session revocation. Access tokens are currently
      long-lived (24h) bearer JWTs with no server-side revocation — logging
      out or deactivating a user doesn't invalidate outstanding tokens.
- [ ] Password reset / forgot-password flow (currently only an admin, or
      the user themself via their existing password, can change it).
- [ ] Team admins in the JSON API. The web UI lets a member flagged
      `team_memberships.is_team_admin` do admin-level work on that one team
      (rocks, issues, to-dos, scorecards, meetings, the team's roster, new
      accounts on it). The API (app/api/crud_router.py, routes.py,
      users_router.py, vto_router.py) still treats those writes as org
      Admin only and doesn't know about team admins. Teach `write_roles` /
      `edit_roles` and app/api/scoping.py a per-team check if the API is
      ever used for real writes.
- [ ] Long-term audit trail. The Activity log (app/core/activity.py) now
      records every add/edit/delete with who + when, including role changes
      and deletes - but it's pruned after ACTIVITY_RETENTION_DAYS (90) and
      every role can read it. If districts need a compliance-grade audit
      record, keep a separate admin-only, non-pruned copy (or export).
- [ ] Content-Security-Policy header. Not set yet - the templates rely on
      inline htmx `hx-on::` attributes and two inline scripts in base.html
      (CSRF header injection, and the pre-paint theme snippet that has to
      run before first paint to avoid a flash of the wrong theme), so a CSP
      tight enough to matter would need those moved to external JS first
      (the theme snippet would need a nonce or hash, since it must stay
      inline).
- [ ] Login rate limiting is IP-keyed only (10 failed attempts / 15 min,
      see app/core/rate_limit.py). Blunts single-source brute force, but
      an attacker spraying many accounts from many IPs isn't slowed down,
      and a NAT'd network (e.g. a whole school building) shares one bucket.
      Consider adding a per-account counter alongside the per-IP one if
      targeted-account attacks turn out to be the bigger risk in practice.
      Also in-memory/per-process - fine for a single on-prem instance, not
      distributed-safe if this ever runs multi-worker/multi-instance.

## Data Model

- [ ] Teams: a district-wide view. Everything is per team now (each with
      its own VTO, rocks, scorecards, ...); there's no org-level VTO or
      roll-up report across teams. EOS usually has a company-level VTO that
      department teams' VTOs hang off - consider one that isn't tied to a
      team (admin-edited, readable by all), or a cross-team dashboard.
- [ ] Activity feed + teams: "last seen" is one timestamp per person, so
      opening the feed on one team marks every team's entries as read.
      Entries with no team (user/org changes, plus anything logged before
      teams existed whose record has since been deleted) are shown to admins
      under "All teams" only - so a team admin never sees the "user created"
      entries for accounts they added to their team. A per-team "last seen" would need a small table.
- [ ] JSON API scoping is by org/team only. The web UI is stricter in a few
      ways the API doesn't enforce: an owner/occupant must be a *member* of
      the row's team (the API only checks they're in the org); a seat's
      parent must be on the same team; a measurable's owner must be on its
      scorecard's team; a to-do's related issue must be on the to-do's team.
      Share one validation layer if the API is ever used for real writes.
- [ ] Rocks and To-Dos keep their owner when that person is removed from the
      team (they must have an owner, unlike a seat or a scorecard row, which
      are vacated/unowned). Consider letting them be unowned, or prompting to
      reassign.
- [ ] The accountability chart is per team: a seat can only report to a seat
      on its own team, and one whose parent is elsewhere (older data) shows
      at the top of its team's chart. EOS usually hangs department seats off
      Leadership Team seats - add an org-wide "whole chart" view (e.g. under
      All teams) that links seats across teams.
- [ ] Home team (users.team_id) has no UI of its own: it's the first team
      ticked when a user is created, and moves to another of their teams if
      they're removed from it. It only decides which team a non-admin lands
      on before they've picked one. Either add a "home team" picker or drop
      the column once nothing else reads it.
- [ ] People Analyzer: core values ratings are currently a simple boolean
      per value. Real GWC/People Analyzer practice often uses a 3-state
      rating (+ / +- / -). Consider widening `core_values_ratings` if the
      simple boolean turns out to be too coarse in practice.
- [ ] VTO versioning/history. Each team's VTO is currently a single
      current-state row (upsert in place). EOS orgs revisit their VTO periodically
      (quarterly/annually) — consider keeping prior versions instead of
      overwriting.
- [ ] Meetings are run live, not scheduled. Today nobody schedules a meeting
      in the app: the admin tells the team and everyone meets in a room, and
      pressing Play (sidebar; admins and the team's team admins) creates - or reuses a meeting
      scheduled for today - and times its six steps (Segue 5, Rocks 5,
      Scorecard 5, Issues 60, To-Dos 10, Closing 5 min). That will change once
      email notifications and a calendar exist, so everyone knows what's
      scheduled: `scheduled_date` is date-only and would need to become a real
      datetime (also required for the Google/Microsoft calendar sync below),
      and "start meeting" should then pick the scheduled one. The Meetings
      page's "Schedule a meeting" form (and POST /meetings) was removed
      until then; bring it back as part of that work. The page's + button
      starts a meeting (same as the sidebar Play button) for now.
- [ ] Live-meeting follow-ups: step lengths are fixed in
      app/core/meeting_session.py (make them per-team settings); only admins
      (and that team's team admins) see the steps - members/viewers could get a read-only live view of the
      current step; a Meetings-page report of step times over several
      meetings (which step runs over, and by how much); "today" is the
      server's date, not the district's time zone.
- [ ] Seat vacancy reporting — a quick endpoint/view listing seats with no
      current `user_id`, useful for accountability-chart gap analysis.
- [ ] Google/Microsoft calendar integration (planned for later). Should be
      an optional sync layer bolted onto Meeting (external event ID +
      push/pull), not baked into the core domain model — consistent with
      the on-prem/no-required-external-deps rule in CLAUDE.md. Requires
      the scheduled_date -> datetime change above first.
- [ ] Notes on Rocks/Issues/To-Dos are a single free-text field with no
      author, timestamp, or history (last save wins, and two people editing
      at once overwrite each other). If teams want a running log, make it
      a note/comment table (who + when) instead of one column. Also: notes
      are readable by every role in the org, including viewers.

## Web UI

Done - all nine EOS tools have a page: Rocks, Issues, To-Dos, Teams,
Users, Scorecards, Meetings, Seats/Accountability Chart, VTO, People
Analyzer. Nothing left on the original page list; next UI work is
whatever the app actually needs in practice (polish, new workflows)
rather than filling a gap.


- [ ] Scorecards follow-ups: (1) edit a scorecard's name / start date
      after creation (today a wrong start date means delete + recreate);
      (2) reorder measurables (rows follow the order they were added);
      (3) a Reports page with trend charts built from scorecard data (the
      old sparklines were removed on purpose); (4) moving a scorecard to
      another team (today: copy it into the other team, then delete it);
      (5) the REST API's scorecard-entry
      endpoints are admin-only, so owners can't use them to bypass the
      "owner or admin" rule the web UI enforces - revisit if API access
      for owners is ever needed.

- [ ] Activity log follow-ups: filter the feed by type (Rocks, Issues, ...)
      or person; a "For you" view of changes to things you own or were
      assigned (closer to how Teams' Activity works); and show the unread
      indicator on the mobile hamburger button too, since the sidebar
      badge is hidden while the menu is collapsed.


## Ops / Dev Experience

Done: Dockerfile + docker-compose now run the whole app (not just
Postgres), with migrations applied automatically on container start.

- [ ] Automated test suite (pytest). `tests/` has unit tests for the
      current-team rules plus DB-backed route and API tests (access control
      across teams and orgs) that run against a throwaway Postgres database,
      in CI too. Still missing: tests for the other pages' behaviour
      (scorecard maths, notes, activity feed...), migration tests, and
      browser tests - the dropdown-narrowing JS (base.html) is only checked
      by hand.
- [ ] CI pipeline: `.github/workflows/deploy.yml` now runs ruff (E9/F
      only), pytest and a Docker build on every push/PR, and auto-deploys
      `main` to the droplet over SSH. Still missing: type-check (mypy).
- [ ] TLS / reverse proxy. The container serves plain HTTP on :8000, and
      COOKIE_SECURE defaults to false to match. Fine for internal-network
      testing, but before this is trusted with real district data, put a
      reverse proxy (nginx/Caddy) in front with a real TLS cert and flip
      COOKIE_SECURE to true - session cookies aren't marked Secure right
      now, so they'd be sent over plain HTTP if this were ever reachable
      outside a trusted network.
- [ ] The `db` service's Postgres credentials (docker-compose.yml) and
      SECRET_KEY's dev-only fallback are safe-for-testing defaults, not
      production-safe. Copy .env.example to .env and set real values
      before this runs anywhere that matters.
