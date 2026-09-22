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

## Generated documents

Both are produced from the formats the client supplied, filled in from the lead:

- **CAF** (Order Confirmation) — downloaded by the measurement staff at stage 5, signed
  by the client, and uploaded back alongside the final measurement.
- **Warranty certificate** — downloaded by the field manager at stage 8, signed, and
  uploaded back before the project is saved as complete.
