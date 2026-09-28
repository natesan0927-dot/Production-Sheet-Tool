# Titans Windows — CRM

A lead-to-handover CRM for Titans Windows, a uPVC windows & doors manufacturer in
Chennai. Every lead moves through one nine-stage journey, and each stage belongs to
exactly one role:

```
LEAD CREATED → ROUGH MEASUREMENT → QUOTATION → FOLLOW-UP / WON-LOST
→ CAF & FINAL MEASUREMENT → PRODUCTION → SITE FABRICATION STATUS → INSTALLATION → WARRANTY & HANDOVER
```

A lead and a customer are the same record — the customer's details are entered once and
carry through quotation, order, production, dispatch and warranty.

## Roles

| Role | Tabs | Owns |
| --- | --- | --- |
| Sales Executive | Dashboard, Leads, Sales Pipeline, Sales Target, Follow-up, Lost Opportunities, Completed Projects | Lead Created, Won/Lost |
| Measurement Staff | Rough Measurements, Final Measurements, Production Sheet Validation | Rough Measurement, CAF & Final Measurement, production sheet approval |
| Quotation Staff | Quotation Upload | Quotation |
| Accounts Department | Accounts, Installation | Ledgers, invoice charges, statements; paying the outsourced installers |
| Production Staff | Production, Site Fabrication Status | Production, Site Fabrication Status |
| Field Manager | Warranty & Handover | Warranty & Handover |
| Super Admin | every tab above, plus Employees and Summary for the Day | every stage, across all sales executives |

## Quick start (Windows / PowerShell)

```powershell
cd D:\Projects\Titans
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
copy .env.example .env            # defaults work out of the box
.\venv\Scripts\python manage.py migrate
.\venv\Scripts\python manage.py seed_employees   # the real staff, on ChangeMe@123
.\venv\Scripts\python manage.py runserver
```

Then open http://127.0.0.1:8000/ and sign in with a name from the Employees list (`rahul`,
`natesan`, `admin`…) — capitals do not matter. Everyone starts on `ChangeMe@123` and is asked to
choose their own password the first time.

For a throwaway machine with sample leads and demo logins instead, run `manage.py seed_data`
(the demo password is `Demo@123`). Never run that on a live site.

## Layout

```
apps/accounts    the user model and its six roles, plus login
apps/crm         everything else: Lead, its files, follow-ups, targets, notifications,
                 the stage machine (stages.py) and the PDF documents (pdf.py)
templates/crm/stages/   one template per stage of the journey
templates/pdf/          the CAF and the warranty certificate
```

## Going live

Hosting options, first sign-in, installing it as an app on a phone or desktop, and the recipe for
a real `.apk` — all in **[DEPLOYMENT.md](DEPLOYMENT.md)**.

The short version: it runs for nothing on an Oracle Cloud Always Free machine, or on
PythonAnywhere's free plan if nobody wants to look after a server. Uploaded files go to the local
disk unless `AWS_STORAGE_BUCKET_NAME` is set, in which case they go to any S3-compatible bucket
(Cloudflare R2, Supabase, Backblaze) — which is what makes a host with no permanent disk usable.

## Staff accounts

`python manage.py seed_employees` creates the team. Everyone starts on `ChangeMe@123` and is held
at a change-password screen until they choose their own. The Super Admin adds and removes people
from the **Employees** tab. To clear a demo install and start clean:

```
python manage.py reset_to_live
```

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
