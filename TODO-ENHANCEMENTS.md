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
- [ ] Seat vacancy reporting — a quick endpoint/view listing seats with no
      current `user_id`, useful for accountability-chart gap analysis.

## Web UI

Done: Rocks, Issues, To-Dos, Teams, Users, Scorecard (list + inline edit;
most have a create form; Scorecard has real SVG sparklines). Remaining:
Meetings, Seats/accountability chart (a real org-chart visual, not just
a table — the most involved of what's left), VTO editor, People Analyzer.

## Ops / Dev Experience

- [ ] Automated test suite (pytest). Verification so far has been manual
      curl runs / browser clicks against a live Postgres container, not
      committed tests.
- [ ] CI pipeline (lint, type-check, tests) — none configured yet.
