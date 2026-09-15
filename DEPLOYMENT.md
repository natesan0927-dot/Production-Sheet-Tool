# Deployment Guide — Titans Windows CRM

This system has a small, fully-internal user base (employees only — sales, measurement,
production, dispatch, installation, service staff, and management). There is no public
customer traffic. That changes the deployment priorities: you don't need to plan for
scale, but you *do* need the system to never lose data and to be reachable by field
staff (measurement/installation teams) from their phones on-site, not just inside an
office LAN.

## Recommended setup

**A single small cloud VPS running PostgreSQL, gunicorn, and Caddy, with nightly
backups synced off-server.** This is the simplest option that is still safe:

| Piece | Choice | Why |
|---|---|---|
| Server | 1 small VPS (1–2 vCPU, 2 GB RAM) — DigitalOcean, Hetzner, AWS Lightsail, or a local Indian provider | Ten to a few dozen internal users need almost no horsepower. ~$6–12/month. |
| Database | PostgreSQL (not SQLite) | Safe concurrent writes, proper backups via `pg_dump`. Already wired up — just set `DATABASE_URL`. |
| App server | `gunicorn` behind `Caddy` as a reverse proxy | Caddy gets you free, automatic HTTPS in about 3 lines of config — important since field staff will open the site from mobile data, not just office Wi-Fi. |
| Static files | WhiteNoise (already configured in `settings.py`) | No separate static file server needed. |
| Process supervision | `systemd` service | Restarts the app automatically if it crashes or the server reboots. |

This is cheap, low-maintenance, and matches the spec's requirement that salespeople,
measurement staff and installation teams use the system from their phones.

**No-cloud-spend alternative:** run it on a spare office PC with
[Tailscale](https://tailscale.com) (free for small teams) instead of a VPS, so field
staff connect over a private mesh VPN without exposing anything to the public internet.
Trade-off: someone has to keep that PC powered on, patched, and its disk healthy —
there's no managed infrastructure behind it, so backups matter even more here.

## Why not SQLite in production

SQLite (the zero-setup default this project ships with) is fine for local development
and even for a first pilot with a couple of users, but Django's SQLite backend locks
the whole database file on writes — fine at low concurrency, but several staff saving
records at the same moment (e.g. everyone starting their day and logging in / updating
leads) can start hitting `database is locked` errors. Postgres removes that ceiling
entirely and costs nothing extra to run. Switch by setting `DATABASE_URL` in `.env`,
e.g.:

```
DATABASE_URL=postgres://titans_user:some-strong-password@localhost:5432/titans_crm
```

## Data safety: three independent layers

Losing business data (leads, quotations, orders, production records) is the one thing
this deployment must never do. The project layers three independent safety nets so
that no single failure loses data:

1. **The database itself** — the single source of truth for every record.
2. **Automatic server-side backups** — `python manage.py backup_now` dumps the full
   database and zips every uploaded/generated file (photos, quotations, certificates)
   into `backups/snapshots/`. Schedule it nightly:
   - **Windows**: run `scripts\schedule_backup.ps1` once (from an elevated PowerShell
     prompt) to register a 2 AM daily Task Scheduler job.
   - **Linux**: add a cron entry, e.g. `0 2 * * * /path/to/venv/bin/python /path/to/manage.py backup_now`.
   - **Critical last step**: a backup that lives on the same disk as the database
     protects against nothing. Sync the `backups/` folder off the server every night —
     the cheapest reliable option is [rclone](https://rclone.org) to Backblaze B2
     (~$0.005/GB/month), or simply pointing a OneDrive/Google Drive desktop sync client
     at the folder. Keep the last ~14 daily snapshots and a handful of monthly ones.
   - Every generated business document (quotations, Customer Acquisition Forms,
     handover certificates, warranty certificates...) is *also* mirrored in real time
     to `DOCUMENT_BACKUP_ROOT` (see `.env`) as soon as it's created — point that at a
     mapped network drive or a synced cloud folder for a second, independent copy of
     documents specifically, separate from the nightly full-database snapshot.
3. **Automatic local copies on every employee's own machine** — whenever someone saves
   a major record (customer, lead, quotation, order, measurement, production sheet,
   dispatch, installation, warranty, service complaint...), their browser immediately
   downloads a PDF or Excel copy of it to their own PC (see "Local copy on save" in
   `README.md`). Even in a worst-case total server loss, the most recent state of most
   records is already sitting on multiple employees' machines and can be manually
   re-entered if it ever truly came to that.

None of these layers is a substitute for the others — the nightly backup protects
against the server dying; the local downloads protect against the highly unlikely case
where both the server *and* its backups are lost at once.

## Restoring from a backup

- **SQLite snapshot** (`backups/snapshots/db_<timestamp>.sqlite3`): stop the app, copy
  the snapshot over `db.sqlite3`, restart.
- **PostgreSQL dump** (`backups/snapshots/db_<timestamp>.sql`): `psql <database> < backups/snapshots/db_<timestamp>.sql` on an empty database, then restart the app.
- **Media snapshot** (`backups/snapshots/media_<timestamp>.zip`): unzip over the
  `media/` folder.

Test a restore occasionally — a backup nobody has ever restored from is not a backup
you can trust.

## Production checklist

1. `DEBUG=False` in `.env`.
2. A long random `DJANGO_SECRET_KEY` (generate one, don't reuse the dev key).
3. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` set to your real domain.
4. `DATABASE_URL` pointing at PostgreSQL.
5. `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`
   once HTTPS is in place (Caddy gives you this automatically).
6. `python manage.py collectstatic --noinput` after each deploy.
7. `python manage.py migrate` after each deploy.
8. Nightly `backup_now` scheduled **and** verified to actually be leaving the server
   (step 2 above — this is the step people forget).
9. Create real employee accounts and assign roles (Groups) instead of using the
   `admin` superuser for daily work — see "Roles & permissions" in `README.md`.
