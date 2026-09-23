# Titans Windows — CRM

A lead-to-handover CRM for Titans Windows, a uPVC windows & doors manufacturer in
Chennai. Every lead moves through one eight-stage journey, and each stage belongs to
exactly one role:

```
LEAD CREATED → ROUGH MEASUREMENT → QUOTATION → FOLLOW-UP / WON-LOST
→ CAF & FINAL MEASUREMENT → PRODUCTION → SITE FABRICATION STATUS → WARRANTY & HANDOVER
```

A lead and a customer are the same record — the customer's details are entered once and
carry through quotation, order, production, dispatch and warranty.

## Roles

| Role | Tabs | Owns |
| --- | --- | --- |
| Salesperson | Dashboard, Leads, Sales Pipeline, Sales Target, Follow-up, Lost Opportunities, Completed Projects | Lead Created, Won/Lost |
| Measurement Staff | Rough Measurements, Final Measurements, Production Sheet Validation | Rough Measurement, CAF & Final Measurement, production sheet approval |
| Accounts Department | Quotations, Confirmed Orders | Quotation |
| Production Staff | Production, Site Fabrication Status | Production, Site Fabrication Status |
| Field Manager | Warranty & Handover | Warranty & Handover |
| Super Admin | every tab above | every stage, across all salespeople |

## Quick start (Windows / PowerShell)

```powershell
cd D:\Projects\Titans
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
copy .env.example .env            # defaults work out of the box
.\venv\Scripts\python manage.py migrate
.\venv\Scripts\python manage.py seed_data     # demo users + sample leads
.\venv\Scripts\python manage.py runserver
```

Then open http://127.0.0.1:8000/ and sign in. The demo accounts are listed on the
login page; the password for all of them is `Demo@123`.

## Layout

```
apps/accounts    the user model and its six roles, plus login
apps/crm         everything else: Lead, its files, follow-ups, targets, notifications,
                 the stage machine (stages.py) and the PDF documents (pdf.py)
templates/crm/stages/   one template per stage of the journey
templates/pdf/          the CAF and the warranty certificate
```

## Deploying to Render

The existing Render web service keeps working with these settings.

**Build Command**

```
pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput && python manage.py seed_data
```

**Start Command**

```
python manage.py seed_data && gunicorn titans_crm.wsgi:application --bind 0.0.0.0:$PORT
```

**Environment variables**

| Key | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | a long random string |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `<your-app>.onrender.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://<your-app>.onrender.com` |
| `DATABASE_URL` | the Render PostgreSQL internal URL |
| `SECURE_SSL_REDIRECT` / `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | `True` |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | your own Super Admin login, created on first deploy |

### First deploy after the rebuild — read this

This version replaced the old system's database design. A database that still holds the old
tables is refused on purpose, with the message *"This database still holds the previous version
of Titans CRM…"*, and nothing in it is touched.

To start fresh, add the environment variable **`RESET_LEGACY_SCHEMA` = `true`** and deploy once.
That permanently deletes the old data and builds the new tables. After that it does nothing (it
only acts when the old tables are present), so it is safe to leave or remove. Alternatively, point
`DATABASE_URL` at a new, empty database.

### Free plan caveat

Uploaded files (quotations, signed CAFs, production sheets, receipts) are stored on the service's
disk, which Render's Free plan wipes on every deploy or restart. The generated CAF and warranty
certificate are unaffected — they are built on demand from `documents/`. For real use, move to the
Starter plan and attach a persistent disk mounted at the project's `media/` folder.

## Generated documents

Both are produced from the formats the client supplied, filled in from the lead:

- **CAF** (Order Confirmation) — downloaded by the measurement staff at stage 5, signed
  by the client, and uploaded back alongside the final measurement.
- **Warranty certificate** — downloaded by the field manager at stage 8, signed, and
  uploaded back before the project is saved as complete.

## The walkthrough

Each person gets a short narrated introduction the first time they sign in, written
for their own role, followed by a guided tour of their own tabs. Both are skippable,
both are recorded as seen so they only happen once, and both can be replayed at any
time from the **Guide** tab in the sidebar.

- The narration is spoken by the browser's own speech synthesis. There is no audio
  file to ship, no third-party service, and nothing to pay for. Browsers will not
  start a voice without a click, so it opens on a poster with a Play button; the
  script is also printed under the stage, and there is a mute toggle that switches
  the scenes to a timer.
- The scripts live in `apps/crm/guide.py` — one set of scenes per role, plus a
  one-line note for every tab. The tour is generated from the same navigation the
  sidebar renders, so it always covers exactly the tabs that role has.
- The screens playing behind the avatar are in `static/guide/`. Re-take them after
  a visible change with:

      python scripts/capture_guide_shots.py

  That builds a throwaway database, invents a few leads, drives them through every
  stage so each queue has something in it, photographs the screens and writes them
  out. It never touches the working database, so no real customer ever appears in
  those images.

To show the walkthrough to someone again from scratch, clear their flags:

    python manage.py shell -c "from apps.accounts.models import User; User.objects.filter(username='demo_sales1').update(intro_seen_at=None, tour_seen_at=None)"
