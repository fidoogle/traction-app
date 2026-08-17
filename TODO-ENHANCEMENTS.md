# Future Enhancements

Backlog of features and improvements identified while building the app.
Check items off as they're implemented; add new ones as they come up.
When picking up new work, skim this file first — mark anything that's
already done, and consider suggesting the next item if nothing else is
queued.

## Authorization & Access Control

- [ ] Team-scoped data access: a `member`/`viewer` can currently read and
      write EOS content (Rocks, Issues, Todos, Measurables, Meetings, ...)
      belonging to *any* team in the org, not just their own team(s). Add
      row-level scoping so non-admins are restricted to their own team(s).
- [ ] Refresh tokens / session revocation. Access tokens are currently
      long-lived (24h) bearer JWTs with no server-side revocation — logging
      out or deactivating a user doesn't invalidate outstanding tokens.
- [ ] Password reset / forgot-password flow (currently only an admin, or
      the user themself via their existing password, can change it).
- [ ] Audit log for sensitive actions (role changes, deletes).
- [ ] CSRF protection for the web UI beyond SameSite=Lax cookies. Lax
      blocks the cookie on cross-site POST/PATCH/DELETE, which covers the
      common case, but a dedicated CSRF token would be more robust if this
      ever needs to satisfy a stricter security review.

## Data Model

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

## Web UI

Done - all nine EOS tools have a page: Rocks, Issues, To-Dos, Teams,
Users, Scorecard, Meetings, Seats/Accountability Chart, VTO, People
Analyzer. Nothing left on the original page list; next UI work is
whatever the app actually needs in practice (polish, new workflows)
rather than filling a gap.

## Ops / Dev Experience

- [ ] Automated test suite (pytest). Verification so far has been manual
      curl runs / browser clicks against a live Postgres container, not
      committed tests.
- [ ] CI pipeline (lint, type-check, tests) — none configured yet.
