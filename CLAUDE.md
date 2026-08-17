# Traction/EOS App for School Districts

## What this is

A Python application implementing the Traction/EOS (Entrepreneurial Operating
System) business process, adapted for school district administration
(rocks/goals, scorecards, L10 meetings, issues lists, org-chart/accountability
charts, etc.).

## Hard constraints

- **On-premise only.** The app must run fully via Docker on a district's own
  infrastructure. No required external/cloud dependencies — no calls to
  hosted SaaS APIs, cloud databases, or third-party auth providers as a
  condition of core functionality. Anything external must be optional and
  gracefully absent by default.
- **Docker-first deployment.** Ship as Docker images / docker-compose, not as
  a "run pip install and hope" app. Assume the target environment is a
  district's internal network, possibly air-gapped or heavily
  firewall-restricted.
- **Data stays local.** School district data (personnel, meeting notes,
  goals, scorecards) is sensitive; do not introduce telemetry, analytics
  beacons, or outbound calls that transmit district data off-box.

## Stack

- **Backend:** Python, FastAPI
- **ORM:** SQLAlchemy
- **Database:** PostgreSQL (runs as its own container; no managed/cloud DB
  service assumed)

## Implications for how to build things

- Prefer libraries that work offline / vendor their own assets (no
  CDN-loaded JS/CSS/fonts in server-rendered or bundled frontend code).
- Config should default to sane on-prem values (local Postgres via
  docker-compose service name, no external SMTP/OAuth required to boot).
- Auth should support a self-contained local mode (e.g. local
  username/password) — don't make an external IdP mandatory.
- Migrations via Alembic (SQLAlchemy's standard companion) should be part of
  the deployment story, not manual schema edits.
- When adding a new dependency, check whether it phones home or requires an
  internet connection at runtime; avoid it or make it optional if so.
