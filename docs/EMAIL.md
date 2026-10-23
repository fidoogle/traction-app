# Email, calendar invitations and reminders

The app can email people (assignments, reminders, a weekly summary, meeting
invitations and more). **It is off until you set it up, and everything else
works without it.** Mail goes through your district's own mail server; nothing
is sent through, or to, any outside service.

## Turn it on

Set these in the server's environment (a `.env` file next to `docker-compose.yml`
works), then restart:

| Setting | What it is | Default |
|---|---|---|
| `SMTP_HOST` | Your mail relay's address. **Email is on only when this, `SMTP_FROM_ADDRESS` and `BASE_URL` are all set.** | empty (off) |
| `SMTP_PORT` | Its port. | `587` |
| `SMTP_SECURITY` | `starttls` (port 587), `ssl` (port 465) or `none` (a plain internal relay, often port 25). | `starttls` |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Only if the relay needs a login. | empty |
| `SMTP_FROM_ADDRESS`, `SMTP_FROM_NAME` | Who the mail comes from. | `Traction` |
| `BASE_URL` | The address people use to reach the app, e.g. `https://traction.district.org`. Links in emails are built from it. | empty |
| `DEFAULT_TIMEZONE` | Fallback only; the real time zone is set on the Settings page. | `America/Chicago` |
| `EMAIL_MAX_PER_USER_PER_HOUR` | Safety net: most non-account emails one person can get in an hour. | `20` |
| `SMTP_RETRIES`, `SMTP_RETRY_DELAY_SECONDS`, `SMTP_DOWN_COOLDOWN_SECONDS`, `SMTP_TIMEOUT_SECONDS` | How hard to retry (see Reliability). | `2`, `2`, `60`, `10` |

Then, signed in as an admin, open **Settings** and use **Send a test email**. It
goes to your own address, so you can see it arrive.

To try things without sending real mail, start the bundled mail catcher with
`docker compose --profile dev up`, set `SMTP_HOST=mailpit SMTP_PORT=1025
SMTP_SECURITY=none SMTP_FROM_ADDRESS=traction@localhost
BASE_URL=http://localhost:8000`, and read the mail at http://localhost:8025.

## The worker

Emails that go out on a clock (the daily To-Do email, the weekly summary,
meeting reminders, quarter reminders, grouped new-issue alerts, and the
delivery-problem notice) are sent by a second container, **`worker`**, in
`docker-compose.yml`. It starts after the app is healthy, checks once a minute,
and does nothing when email is off. **Run exactly one.** It is safe to restart:
a record of what has been sent stops anything going out twice.

If you turn email on partway through a week, the weekly summary for that week
goes out as soon as the worker next checks, because its scheduled time has
already passed.

## Who gets what

Each person chooses for themselves on **My notifications** (the envelope in the
top bar). Nobody has to configure defaults: they follow from a person's role.

| Email | Who | On by default for |
|---|---|---|
| Account created, password reset | the person | everyone (can't be turned off) |
| A To-Do or Rock is assigned to you | the new owner | members, admins |
| To-Dos due soon or overdue (daily, 7:00) | the owner | members, admins |
| Meeting scheduled / changed / cancelled | the team | everyone |
| Meeting reminder, day before | the team | everyone |
| Meeting reminder, hour before | the team | no one (opt-in) |
| Weekly summary | everyone | everyone |
| Meeting recap, new issues | the team | no one (opt-in) |
| A Rock goes off track | the team's admins | team admins (org admins opt in) |
| Quarter starting / ending | the team's admins | team admins (org admins opt in) |
| A scorecard number missed twice running | owner and team admins | no one (opt-in) |
| System notices (new users, role changes, email failures) | org admins | no one (opt-in) |

Viewers get meeting emails and the summary. The person who made a change is
never emailed about it.

## Time and schedules

- **Time zone.** One per organization, on the Settings page (US Central to begin
  with; daylight saving is handled). Meeting times are typed and shown in it.
- **Weekly summary.** Monday 7:00 unless an admin changes the day and time on
  the Settings page. Once that moment has passed it is sent at the next check,
  at most once per person per week. Admins can also press **Send this week's
  summary now**.
- **Daily To-Do email and quarter reminders.** From 7:00 in the organization's
  time zone. Quarters are calendar quarters (the same `2026-Q4` labels Rocks use):
  a reminder on the first day, and one two weeks before the last.
- **Reminders for meetings.** A day before (sent when the meeting is 22 to 24
  hours away, so a meeting made with less notice is covered by its invitation),
  and optionally an hour before.

## Calendar invitations

- Scheduling a meeting (Meetings page, team admins and admins) emails the team an
  invitation with a standard `.ics` file attached. It opens in **Outlook, Google
  Calendar and Apple Calendar** without any outside connection.
- Changing a meeting sends an update that replaces the earlier entry; cancelling
  sends a cancellation that removes it. (They share a calendar ID and a rising
  sequence number.) Every event carries a 15-minute alert.
- Invitations ask for **no reply** (the app does not read replies), so people
  just add the event.
- Anyone can download a meeting as `.ics` from the Meetings page.
- **Calendar subscription.** On My notifications a person can subscribe their
  calendar app to a private address that lists their teams' upcoming meetings.
  The address is secret: they can replace it or switch it off. Outlook on the
  district network can usually reach it. Google Calendar fetches subscriptions
  from the internet, so it cannot reach a private address, and it refreshes only
  every few hours.
- **"Add to Google / Outlook" links** in invitations are **off by default**,
  because clicking them opens those outside websites. Admins can turn them on in
  Settings. The attached calendar file works without them.

## Reliability

- A send that fails for a reason that may pass (busy server, brief network
  trouble) is tried again twice, after 2 s and 4 s. A refusal that won't pass
  (unknown address, wrong password) is not retried.
- If the mail server cannot be reached at all, the app stops trying for a minute,
  so a long list of emails during an outage fails quickly instead of stalling.
- **A failed email is recorded but not sent again later on its own.** The
  Settings page lists the most recent failures and the last day's counts, and
  admins who opt in to System notices are emailed (once a day) when five or more
  have failed in 24 hours.
- Each person receives at most 20 non-account emails an hour; extras are dropped
  and logged. This only guards against a bug.
- The record of sent emails is kept for 90 days (`NOTIFICATION_LOG_RETENTION_DAYS`).
- Every optional email links to My notifications and carries a
  `List-Unsubscribe` header, which is what mail programs use for their own
  "unsubscribe" button. Account emails say they can't be turned off.

## Privacy: what is in the emails, and what leaves the building

- **Only the mail itself leaves**, and only to your mail server. There is no
  tracking, no images, styles or scripts loaded from anywhere (opening an email
  tells nobody anything), and no analytics.
- The one exception you can enable is the optional "Add to Google / Outlook"
  links, which are ordinary links that go nowhere until someone clicks.
- Emails contain **titles and names**: To-Do, Rock, issue and measurable titles,
  team names, meeting times and places, people's names, and scorecard numbers.
  Passwords are never sent; account emails carry one-time links (48 hours for a
  new account, one hour for a reset).
- Emails **never** contain notes, People Analyzer or accountability-chart content,
  VTO text, or password data. Tests enforce this.
- Email travels through your mail system and people's inboxes, which may be less
  protected than the app. Keep that in mind when deciding who is in the app and
  how much goes in titles.

## Adding an email (for developers)

1. Add a type to `CATALOG` in `app/core/notifications.py` (who may receive it, who
   gets it on by default).
2. Add `templates/email/<name>.txt` and `.html` (copy a similar one; inline styles
   only, nothing loaded from outside).
3. Add sample data in `app/core/email_samples.py`; a test fails until you do.
4. Send it with `notify(...)` after committing the change it reports. It applies the
   person's role and choices, sends each (person, type, subject, period) only once,
   and records the result.
5. `python -m scripts.preview_emails` writes every email to `email-preview/` for a
   look; add `--send you@district.org` to see them in Outlook or Gmail.

The tests that need a database run against the Postgres in `docker-compose.yml`.
