# Titans Windows — CRM / ERP System

A complete CRM + ERP + Production + Installation + Maintenance management system for
Titans Windows, a uPVC Windows & Doors manufacturing company in Chennai, built in
Django. It covers the full business workflow described in the project spec:

```
Customer → Lead → Salesperson Assignment → Site Measurement → Quotation → Follow-up
→ Won/Lost → Order Confirmation → Customer Acquisition Form → Final Measurement
→ Production Planning → Production Sheet → Manufacturing → Quality Check → Dispatch
→ Installation → Final Handover → Warranty → Service/Maintenance
```

Every stage flows automatically into the next — a customer's details, once entered,
are never retyped again through quotation, order, production, dispatch, installation,
handover or warranty.

## Quick start (Windows / PowerShell)

```powershell
cd D:\Projects\Titans
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
copy .env.example .env            # then edit .env if needed (defaults work out of the box)
.\venv\Scripts\python manage.py migrate
.\venv\Scripts\python manage.py seed_data        # default roles, lead statuses, production stages, etc.
.\venv\Scripts\python manage.py createsuperuser
.\venv\Scripts\python manage.py runserver
```

Then open http://127.0.0.1:8000/ and sign in with the superuser account.

For a real deployment (not just local development), see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## Architecture

- **Framework**: Django 5.2, server-rendered templates (Bootstrap 5 + Chart.js via CDN)
  — no separate frontend build step, easy for a small team to maintain.
- **Database**: SQLite by default (zero setup); switch to PostgreSQL for production by
  setting `DATABASE_URL` in `.env` (see DEPLOYMENT.md).
- **Apps** (`apps/`), each owning one part of the workflow:
  - `accounts` — employees, departments, login. Roles are Django Groups (Super Admin,
    Management, Sales Manager, Salesperson, Measurement Staff, Quotation Staff, Admin
    Staff, Production Manager, Production Staff, Quality Control, Dispatch Staff,
    Installation Team, Service/Maintenance Staff), each independently configurable
    with per-model view/add/change/delete permissions from `/admin/auth/group/`.
  - `core` — company profile, all configurable master data (lead sources/statuses,
    lost reasons, competitors, product master, payment terms, production stages, QC
    &amp; installation checklists, service categories, document numbering formats,
    PDF templates), notifications, generic document/attachment storage, and the
    PDF/Excel export engine.
  - `crm` — customers, leads, follow-ups, communication history, lost-lead capture.
  - `measurement` — site measurement requests and independent final measurement.
  - `sales` — quotations (with full version history), order confirmation ("Won"
    workflow), Customer Acquisition Form auto-generation, payments, sales targets.
  - `production` — production sheets, configurable production stages, quality control.
  - `logistics` — dispatch, installation (with Site-Not-Ready handling), handover
    certificate generation.
  - `aftersales` — warranty activation, service/maintenance complaints.
  - `dashboard` — the role-aware home dashboard (stat cards, sales funnel, monthly
    sales chart, "My Tasks").
  - `reports` — monthly sales, lost-lead analysis, production and customer reports,
    each exportable to Excel.
- **Audit trail**: `django-simple-history` tracks every change to Customers and Leads
  (who changed what, old value, new value, when) — visible from each record's admin
  history view.
- **Workflow automation**: status changes trigger the next step automatically (e.g.
  measurement completed → notifies the salesperson; final measurement approved →
  creates the production sheet task; QC approved → creates the dispatch task; dispatch
  marked complete → creates the installation task; installation handover signed →
  generates the warranty certificate) — see each app's `services.py`.
- **PDF/Excel generation**: `xhtml2pdf` (pure-Python, no system dependencies — installs
  cleanly on Windows) renders quotations, order confirmations, Customer Acquisition
  Forms, handover and warranty certificates from HTML templates
  (`templates/core/pdf/pdf_base.html` + per-document templates). Excel exports (`.xlsx`,
  via `openpyxl`) are used for item/line-level data — measurement sheets, production
  sheets.

## "Local copy on save" (per your request)

Since there's no customer-facing traffic to worry about, the priority was making sure
staff never lose their own work. Whenever someone saves one of the major business
records — customer, lead, quotation, order, measurement, final measurement, production
sheet, dispatch, installation, warranty, or service complaint — **their browser
immediately downloads a PDF (for document-style records) or Excel (for records that
are really a table of line items, like measurements and production sheets) copy of
that record straight to their own computer**, no extra click needed. That download is
in addition to the record being saved in the shared database, and a second copy is
also written to a server-side backup folder (`DOCUMENT_BACKUP_ROOT`, see
DEPLOYMENT.md). See `apps/core/exports.py` (the export registry) and
`apps/core/mixins.py` (`AutoLocalExportMixin`) for how this is wired up — any record's
"Download" button on its detail page uses the same mechanism on demand.

*(Note: this intentionally covers the major records employees actually create, not
every minor sub-object like a single follow-up note — downloading a file on every
keystroke-level save would be more annoying than useful. Tell me if you'd like it
extended to specific other records.)*

## Roles & permissions

Run `python manage.py seed_data` once to create the standard roles from the spec as
Django Groups. From `/admin/auth/group/`, Admin can:
- Create additional roles.
- Tick exactly which permissions (view/add/change/delete, per model) each role has.
- Assign employees to one or more roles from `/accounts/employees/`.

List/detail views throughout the app additionally scope data to "my own" records for
non-management roles (e.g. a Salesperson only sees their own leads/orders), enforced
in the view layer (`request.user.has_role(...)`), not just hidden in the UI.

## Everything is configurable, nothing is hard-coded

Company name/logo/address/GST/tax rate, lead sources & statuses, lost reasons,
competitors, the full product master (profile series, glass, hardware, accessories),
payment term templates, document numbering formats (`LEAD-2026-00001` etc.),
production stages, QC and installation checklists, service categories, and the PDF
document templates are all editable from **Settings** (`/core/settings/`, which links
into the relevant `/admin/` screens) — never in source code.

## Running the smoke-tested workflow yourself

1. Create a Customer, then a Lead against them.
2. From the lead, "Request Measurement" → fill in window/door items → "Mark Completed".
3. "Request / Create Quotation" → add line items → save.
4. From the quotation, "Proceed to Won" → fill in the order confirmation form. This
   auto-generates the Customer Acquisition Form PDF.
5. "Start Final Measurement" on the order → fill in items → this creates the
   Production Sheet task automatically once approved.
6. Production Sheet → fill items → Submit → (Production Manager) Approve → this
   creates one task per configured production stage.
7. Mark every stage task "Completed" → a Quality Check is created automatically.
8. Approve the Quality Check → a Dispatch record is created automatically.
9. Fill in dispatch details → "Mark as Dispatched" → an Installation record is created
   automatically.
10. Schedule and complete the installation → generate the Handover Certificate → this
    activates the Warranty automatically.
11. Log a Service Complaint against the customer/order at any point afterwards.

This exact sequence is covered end-to-end by the project's smoke tests, so it's known
to work.
