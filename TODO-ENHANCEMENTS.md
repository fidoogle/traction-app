# Future Enhancements

Backlog of features and improvements identified while building the app.
Check items off as they're implemented; add new ones as they come up.
When picking up new work, skim this file first — mark anything that's
already done, and consider suggesting the next item if nothing else is
queued.

## Authorization & Access Control

- [ ] Team-scoped data access, mostly done: Rocks, Issues, Meetings, Seats,
      People Analyzer, Scorecards and the JSON API are now limited to your
      own teams (admins: every team in the org). Still open: To-Dos (their
      list isn't team-scoped yet - Teams rollout phase 3), the VTO (phase 4),
      and the Dashboard counts + Activity feed (phase 5).
- [ ] Refresh tokens / session revocation. Access tokens are currently
      long-lived (24h) bearer JWTs with no server-side revocation — logging
      out or deactivating a user doesn't invalidate outstanding tokens.
- [ ] Password reset / forgot-password flow (currently only an admin, or
      the user themself via their existing password, can change it).
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

- [ ] Teams rollout (multi-team support), in progress. Done: Phase 0 -
      `team_memberships` (people can be on several teams), the topbar
      current-team switcher, member add/remove on the Teams page; Phase 1 -
      each scorecard belongs to a team (list follows the current team,
      owners must be team members, non-members get 404); Phase 2 - Rocks,
      Issues, Meetings, Org Chart and People Analyzer follow the current
      team and are limited to your own teams, and the JSON API got the same
      scoping (app/api/scoping.py). Next: (3) To-Dos get a team_id;
      (4) one VTO per team; (5) Dashboard + Activity follow the current team.
- [ ] JSON API scoping is by org/team only. The web UI is stricter in three
      ways the API doesn't enforce: an owner/occupant must be a *member* of
      the row's team (the API only checks they're in the org); a seat's
      parent must be on the same team; a measurable's owner must be on its
      scorecard's team. Share one validation layer if the API is ever
      used for real writes. To-Dos are scoped to the org only, until phase 3.
- [ ] Rocks keep their owner when that person is removed from the team (a
      rock must have an owner, unlike a seat or a scorecard row, which are
      vacated/unowned). Consider letting a rock be unowned, or prompting to
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
- [ ] VTO versioning/history. VTO is currently a single current-state row
      per org (upsert in place). EOS orgs revisit their VTO periodically
      (quarterly/annually) — consider keeping prior versions instead of
      overwriting.
- [ ] Meeting model is bare-bones (date + status only). A real L10 meeting
      has a standard agenda (segue, scorecard review, rock review, IDS,
      to-do review, conclude) — consider a MeetingSegment or agenda concept.
      `scheduled_date` is also date-only (no time-of-day) - this would need
      to become a real datetime before Meeting could sync to an actual
      calendar slot (see Google/Microsoft calendar integration below).
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
