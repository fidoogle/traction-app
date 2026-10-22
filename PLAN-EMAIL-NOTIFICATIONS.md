# Plan: Email notifications and calendar invites

Status legend: `[ ]` not started, `[x]` done (committed and verified).
Work one phase at a time. Each phase ends with tests passing and a commit
(per CLAUDE.md). Anything that comes up but is out of scope goes to
`TODO-ENHANCEMENTS.md`.

## Goals

- Tell people only what needs their attention, with few emails per person.
- Let each user choose which optional emails they get.
- Let a user put a team meeting on their Outlook / Google / Apple calendar
  from an email (and from the app).

## Constraints (from CLAUDE.md)

- **Off by default.** The app must boot and work with no SMTP configured.
  The UI shows a clear "Email is not configured" state.
- **On-prem.** Mail goes through the district's own SMTP relay. No hosted
  email APIs (SendGrid, SES, etc.) and no third-party calendar APIs.
- **Data stays local.** Email bodies are short and link back to the app
  rather than repeating issue or personnel text. No tracking pixels, no
  click-tracking redirects, no remote images.
- **Docker-first.** Any new process is a compose service. Schema changes
  are Alembic migrations.

## Decisions already made

| Topic | Decision |
|---|---|
| Transport | SMTP via stdlib `smtplib` / `email` (no new dependency). Config by env vars. |
| Scheduler | A separate `worker` service in docker-compose running the same image with a different command. Single instance, so no duplicate-send races. |
| Idempotency | `notification_log` table with a unique key per (user, type, subject, period). |
| Calendar | `.ics` attachment/download (RFC 5545 / iTIP) is the core. "Add to Google / Outlook" web links are optional extras. No OAuth or calendar API sync (that stays in TODO-ENHANCEMENTS). |
| Links | A new `BASE_URL` setting is needed to build absolute links in emails. |

## Open decisions (answer before the phase that needs them)

1. ~~Digest day and time~~ Decided: one schedule for everyone (not per-user). Default Monday 7:00 in the org timezone; an admin may change the day and time. *(Phase 6)*
2. ~~Org-wide defaults set by admins~~ Decided: no. Admins configure nothing; defaults come from the catalog and user role (see Phase 3). *(Phase 3)*
3. ~~Meeting timezone~~ Decided: one org-wide timezone, default `America/Chicago` (US Central; San Antonio is in the same zone). *(Phase 5)*
4. ~~Meeting length and reminders~~ Decided: default length 90 minutes, matching the live meeting's six timed steps (5+5+5+60+10+5 in `app/core/meeting_session.py`). Reminder email 24 h before (on by default). A 15-minute alert is built into the calendar event itself, so no email is needed for short-notice reminders. A 1 h reminder email is opt-in. *(Phase 5)*

---

## Notification catalog

Defaults: **On** = enabled for new users, **Opt-in** = off until the user turns it on,
**Always** = cannot be turned off.

| Key | Email | Recipient | Default | Phase |
|---|---|---|---|---|
| `account_welcome` | Account created, link to set a password | New user | Always | 2 |
| `password_reset` | Reset link | Requesting user | Always | 2 |
| `todo_assigned` | To-Do assigned to you | Owner (not if self-assigned) | On | 4 |
| `owner_reassigned` | Rock or Issue reassigned to you | New owner | On | 4 |
| `todo_due` | To-Dos due within 2 days or overdue (one email per day, lists all) | Owner | On | 4 |
| `meeting_invite` | Meeting scheduled or changed, with .ics | Team members | On | 5 |
| `meeting_reminder` | 24 h before | Team members | On | 5 |
| `meeting_reminder_1h` | 1 h before | Team members | Opt-in | 5 |
| `meeting_cancelled` | Meeting cancelled, with .ics cancel | Team members | On | 5 |
| `weekly_digest` | Open To-Dos, Rocks at risk, off-track scorecard items | Members and team admins | On | 6 |
| `rock_off_track` | A Rock was set Off Track | Team admins | On for team admins (opt-in for org admins) | 7 |
| `scorecard_missed` | Measurable missed goal N weeks running | Measurable owner, team admins | Opt-in | 7 |
| `issue_added` | New issue on the team list | Team members | Opt-in | 7 |
| `meeting_summary` | Recap after a meeting is finished | Team members | Opt-in | 7 |
| `quarter_reminder` | Rock-setting reminder at quarter start / end | Team admins | On for team admins (opt-in for org admins) | 7 |
| `admin_system` | New user, role change, email delivery failures | Admins | Opt-in | 7 |

Role rules:

- **Viewer**: `account_welcome`, `password_reset`, meeting emails, digest.
  No assignment emails (viewers cannot own items).
- **Member**: everything above for items they own.
- **Team admin**: member set, plus the team-level opt-in types for their teams.
- **Admin**: member set, plus `admin_system`. Not team-level mail for every team.

A user only receives team-level mail for teams they belong to (use
`TeamMembership`, as `app/core/team_access.py` does).

---

## Phase 1: Email plumbing

Goal: the app can send a message through SMTP, and nothing else changes.

- [x] Add settings to `app/config.py`: `smtp_host`, `smtp_port`, `smtp_username`,
      `smtp_password`, `smtp_security` (`starttls` | `ssl` | `none`), `smtp_from_address`,
      `smtp_from_name`, `base_url`. Email is enabled only when host, from-address
      and base URL are all set (`settings.email_enabled`).
- [x] `app/core/email.py`: `send_email(to, subject, text_body, html_body=None, attachments=())`.
      Plain text always, HTML optional. Timeout on the connection. Never raises into
      a request handler; returns success or failure and logs.
- [x] Template system for emails: Jinja2 (already used by the app) under
      `app/templates/email/`, one text and one HTML template per type, shared
      base layout. Inline CSS only, no remote assets.
- [x] Pass the new env vars through `docker-compose.yml` and document them in
      `.env.example`.
- [x] Admin-only "Send test email" action (in a new Settings page or on the Users page).
      Shows the "not configured" state when disabled.
- [x] Dev aid: document running a local catch-all SMTP container (e.g. MailHog or
      Mailpit) under a compose `profiles: [dev]` entry so nothing leaves the machine
      while testing.
- [ ] Tests: sending is a no-op when disabled; a fake SMTP server (or monkeypatched
      `smtplib`) receives the right headers and body; failures are swallowed and logged.

Note: the Settings page is at `/settings` (admin only) and has the send-test button. The
unit tests in `tests/test_email.py` pass; its four route tests need Postgres and have not
yet been run (Docker Desktop would not start). Run `pytest tests/test_email.py` once the
database is up, then tick the Tests box. The same routes were exercised by hand with the
sign-in dependency stubbed.

Done when: a test email reaches the dev mail catcher and the app boots with no SMTP settings.

## Phase 2: Account emails (welcome and password reset)

Goal: new users get a way in without an admin reading out a password.

First check how `create_user` in `app/web/users_routes.py` sets the initial password
today, and keep that path working when email is off.

- [x] Migration: `password_reset_tokens` table (user id, hash of token, expires_at,
      used_at). Store only a hash of the token.
- [x] Token helper in `app/core/security.py`: create, verify, expire (e.g. 48 h for
      welcome, 1 h for reset), single use.
- [x] Routes: `GET/POST /set-password/{token}`, `GET/POST /forgot-password`.
      Forgot-password responds identically whether or not the email exists, and is
      rate limited with the existing `rate_limit.py`.
- [x] Welcome email sent when an admin or team admin creates a user and email is
      enabled. Contains a one-time link, never a password.
- [x] Admin action "Resend welcome email" on the Users page.
- [x] If email is disabled, keep the current manual flow and show that in the UI.
- [ ] Tests: token expiry, reuse, wrong token, enumeration-safe response, rate limit.

Note: `tests/test_password_tokens.py` (28 tests) passes against a throwaway SQLite stand-in,
not Postgres (Docker would not start). Tick the Tests box here and on Phase 1 after
`python -m pytest -q` passes against the real database. Team admins can add users and the
new user gets the welcome email; "Resend welcome email" is admin-only. The JSON API's
user creation (`app/api/users_router.py`) does not send email.

Done when: create a user, receive the link, set a password, log in.

## Phase 3: Preferences and notification log

Goal: the data model that every later phase relies on.

- [x] Migration: `notification_preferences` (user id, notification key, enabled)
      or a JSONB column on `users`. Prefer the table so keys can be added without
      migrations touching users. Missing row means "use the default from the catalog".
- [x] Migration: `notification_log` (id, user id, key, `subject` (e.g. `todo:<id>`, "" if none), `period`
      (e.g. `2026-W43`, a meeting's sequence; "" if none), status pending/sent/failed, error,
      created_at) with a unique constraint on (user id, key, subject, period).
- [x] `app/core/notifications.py`: one registry that holds the catalog above
      (key, label, default, allowed roles, always-on flag). Everything else reads it.
- [x] `notify(user, key, context)` helper: checks role and preference, checks the
      log for a duplicate, renders, sends, records the result.
- [x] "My notifications" page: one toggle per type the user's role may receive,
      grouped (Assignments, Meetings, Summaries, Team alerts). Always-on items are
      shown but locked. Includes calendar-feed link (Phase 5) later.
- [x] No admin configuration of notification defaults. Defaults are computed by the
      system: `default_for(user, key)` in the registry returns on/off from the catalog
      entry and the user's role (and team-admin status), so a new user gets a sensible
      set automatically (e.g. viewers get meeting emails and digest only; team admins
      get the team-level types that apply to them). Users can still override their own
      toggles on "My notifications". Changing a catalog default later applies to anyone
      who hasn't overridden it, since only explicit overrides are stored.
- [x] Log retention: prune old rows with the same pattern as `activity_retention_days`.
- [ ] Tests: role filtering, preference override, duplicate suppression.

Built as: `app/core/notifications.py` (catalog, "hats" = role plus team_admin, `types_for`,
`set_preference`, `notify`, `prune_log`), `app/models/notification.py`, the page at
`/notifications` (envelope icon in the top bar), migration `d5f8b2c0e4a7`. Later phases call
`notify(db, user, key, subject_line=..., template=..., context=..., subject=..., period=...)`
after committing their change. It skips quietly when email is off, the role can't get the
type, or the person turned it off; a claim row stops duplicates; a failed send can be
retried by calling it again. The calendar-feed link on the page waits for Phase 5.
`tests/test_notifications.py` (25 tests) passes on the SQLite stand-in, not yet on Postgres.

## Phase 4: Assignment and due-date emails

Goal: first real notifications. Event-driven plus one daily job.

- [ ] Hook `todo_assigned` into To-Do create and owner-change (`todos_routes.py`,
      `quick_add_routes.py`, and API routes if they create To-Dos). Skip when the actor
      is the new owner.
- [ ] Hook `owner_reassigned` into Rock and Issue owner changes.
- [ ] Send after the DB commit, not inside the transaction.
- [ ] Worker service: add `worker` to `docker-compose.yml`, entrypoint `python -m app.worker`,
      loop with a simple tick (e.g. every minute), graceful shutdown, shares the DB.
- [ ] Daily `todo_due` job: per owner, one email listing items due within 2 days or
      overdue; the log key uses the date so it sends at most once per day; skip if
      the list is empty.
- [ ] Tests: assignment sends once, self-assignment sends nothing, due job is
      idempotent across two runs.

## Phase 5: Meeting scheduling, invites and calendar

This phase includes the calendar feature and the scheduling change already listed in
`TODO-ENHANCEMENTS.md` ("Meetings are run live, not scheduled").

### 5a. Scheduling model

- [ ] Migration: change `meetings.scheduled_date` (Date) to a real timestamp
      (`scheduled_start` with timezone) plus `duration_minutes` (default 90), optional `location`
      (room name or video link). Convert existing rows to a default time.
- [ ] Add `ical_uid` (stable UUID) and `ical_sequence` (integer, bumped on each
      change) to meetings. Calendars use these to update rather than duplicate.
- [ ] Org-wide timezone setting stored with the organization, default `America/Chicago`
      (IANA name, so daylight saving is handled; do not hard-code a fixed UTC-6 offset).
      Admin can change it. Meeting times are entered and displayed in this zone,
      stored in UTC, and written to `.ics` as UTC so every calendar converts correctly.
      Use stdlib `zoneinfo`; the Docker image needs the `tzdata` package since slim
      images often lack zone data.
- [ ] Bring back the "Schedule a meeting" form and `POST /meetings`. Starting a
      meeting (Play button) should pick up the scheduled one for today.
      Update `app/core/meeting_session.py` and its tests.
- [ ] Edit and cancel a scheduled meeting. Editing time/location bumps the sequence;
      cancel sets status cancelled.
- [ ] Tests: migration of existing data, start-meeting picks the scheduled meeting,
      permissions (admins and that team's team admins only).

### 5b. Calendar files (.ics)

- [ ] `app/core/ical.py`: build `VCALENDAR` with one `VEVENT` (UID, SEQUENCE, DTSTAMP,
      DTSTART/DTEND in UTC, SUMMARY, LOCATION, DESCRIPTION with the app link, URL,
      ORGANIZER, STATUS, optional `VALARM`). Escape and fold lines per RFC 5545.
      Hand-written, no dependency, so there is nothing to check for phoning home.
- [ ] Use `METHOD:REQUEST` for invites and updates, and `METHOD:CANCEL` (with the
      same UID and a higher SEQUENCE) for cancellations.
- [ ] Authenticated download `GET /meetings/{id}/calendar.ics` ("Add to calendar"
      button on the Meetings page and the meeting detail).
- [ ] Tests: output checked against a fixed sample; round-trip parse with a throwaway
      parser in tests; line folding and escaping of commas, semicolons, newlines.

### 5c. Calendar emails

- [ ] `meeting_invite`: email with the .ics attached (`text/calendar; method=REQUEST`)
      so Outlook and Apple Mail show Accept / Decline and Gmail shows "Add to
      calendar". Body also has plain details and a link to the app.
- [ ] Optional links in the email body, built as plain URLs (no data sent anywhere
      until the user clicks):
      - Google: `https://calendar.google.com/calendar/render?action=TEMPLATE&text=...&dates=...`
      - Outlook web: `https://outlook.office.com/calendar/0/deeplink/compose?...`
      - A link to the app's own `.ics` download (needs login).
      Show these links only if an admin setting "include web calendar links" is on,
      since they point at external sites. Default off for air-gapped sites; the
      attachment alone is enough there.
- [ ] `meeting_cancelled` with the cancel .ics.
- [ ] Add a 15-minute `VALARM` to every `.ics` so calendar apps alert on their own.
- [ ] `meeting_reminder` via the worker: 24 h before (default), and 1 h before for users
      who opted in. Log key includes the meeting id and sequence so a rescheduled
      meeting reminds again.
- [ ] Changed meetings re-send the invite with the new sequence (Phase 3 helper,
      key `meeting_invite`, period key = sequence).
- [ ] Tests: attachment present with right content type and METHOD; update uses the
      same UID with a higher SEQUENCE; reminders not duplicated; cancelled meetings
      stop reminders.

### 5d. Optional calendar subscription feed

- [ ] Per-user private feed URL `/calendar/{token}.ics` listing the user's teams'
      upcoming meetings, which they can subscribe to in Outlook or Google ("from URL").
      Token is random, revocable and regenerable from "My notifications".
      Google refreshes subscribed calendars slowly (hours), so say that in the UI.
- [ ] Only for sites where the app URL is reachable from the user's calendar client
      (Outlook desktop on the district network is the usual case). Note that Google
      Calendar's servers fetch the URL themselves, so this will not work on a private
      network; document that rather than hiding it.
- [ ] Tests: token auth, revoke, no data from teams the user isn't in.

## Phase 6: Weekly digest

- [ ] Digest builder: for one user, gather open To-Dos (due soon or overdue), Rocks
      Off Track or At Risk, and scorecard items off goal, scoped to their teams. Return
      nothing if there is nothing to say, and send no email.
- [ ] Digest schedule is an org setting: day of week and time, default Monday 7:00 in
      the org timezone. One schedule for all users, no per-user setting. Stored in an
      org-level settings row (add alongside the timezone field in Phase 5, or a small
      migration here if Phase 6 comes first).
- [ ] Admin-only form on a Settings page to change the day and time, validated
      (day 0-6, time on a 15-minute step). Changes apply from the next run.
- [ ] Worker checks each tick whether the scheduled moment this week has passed and no
      digest has gone out for this ISO week (log key = ISO week). If the worker was
      down at the scheduled time it sends on its next tick, not skipping the week.
      If an admin moves the schedule to later this week after the digest already sent,
      it does not send twice.
- [ ] Optional: admin "Send digest now" button, which uses the same log key so it counts
      as this week's digest.
- [ ] Digest respects role: viewers get the read-only summary, members get items
      they own, team admins also get team totals.
- [ ] Tests: content per role, empty digest sends nothing, once per week, schedule
      change honored, daylight-saving week boundaries.

## Phase 7: Opt-in team alerts

One notification at a time, each small and separately committed.

- [ ] `rock_off_track`: fire on status change to Off Track; recipients are the
      Rock's team admins.
- [ ] `scorecard_missed`: evaluate when weekly entries are saved; N consecutive misses
      (start with 2); log key includes the week so it fires once.
- [ ] `issue_added`: batch within a short window (e.g. combine adds made in the same
      5 minutes) so a busy meeting doesn't flood inboxes.
- [ ] `meeting_summary`: sent when a meeting is finished; lists decisions, new To-Dos,
      and issues left open. Link to the app for detail.
- [ ] `quarter_reminder`: worker job at quarter boundaries; needs the org's fiscal
      quarter definition (check how Rocks track quarters first).
- [ ] `admin_system`: new user, role change, repeated delivery failures.

## Phase 8: Hardening and documentation

- [ ] Rate limit and cap per-user sends per hour as a safety net against loops.
- [ ] Retry policy for transient SMTP failures (a few tries with backoff, then
      mark failed in the log).
- [ ] Unsubscribe: every optional email links to "My notifications" and carries a
      `List-Unsubscribe` header pointing there. Always-on types are marked as such.
- [ ] Admin view of recent failures from `notification_log`.
- [ ] Check emails render in Outlook, Gmail and a plain-text client (text version
      reads fine on its own).
- [ ] Privacy pass: confirm no email includes personnel evaluations, People Analyzer
      content, or full issue text.
- [ ] Docs: README or deployment section covering SMTP settings, `BASE_URL`, the
      worker service, timezone, calendar behavior, and what is sent externally (only
      the mail itself; web calendar links are opt-in).
- [ ] Update `TODO-ENHANCEMENTS.md`: remove the "Meetings are run live" item once
      Phase 5 lands, and keep the Google/Microsoft calendar sync item as separate
      future work.

---

## Order and dependencies

```
1 Plumbing -> 2 Account emails
          \-> 3 Prefs + log -> 4 Assignment/due (adds worker)
                           \-> 5 Scheduling + calendar -> (5d feed)
                           \-> 6 Digest
                           \-> 7 Opt-in alerts
                                        8 Hardening runs alongside, finishes last
```

Phases 4, 5 and 6 are independent of each other once 3 is done. Suggested order is
1, 2, 3, 4, 5, 6, 7, 8. Phase 5 is the largest because of the schema change.

## Checklist of things easy to miss

- [ ] `BASE_URL` set, or links in emails are broken
- [ ] Emails sent after commit, never inside a failed transaction
- [ ] Actor never emailed about their own action
- [ ] Deleted users and removed team members stop receiving mail
- [ ] Email address changes (if editable) update the welcome/reset flow
- [ ] Timezone handling and daylight saving in .ics and reminders
- [ ] Meeting edits bump `SEQUENCE`; cancels reuse the UID
- [ ] Worker restarts do not resend (log unique key)
- [ ] Everything works with email disabled
- [ ] No outbound request is made by the app itself except SMTP
- [ ] Tests for each phase, commit per phase
