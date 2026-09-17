"""
Plain-language, per-role content for the "Guide" page (apps.core.views.guide).
Keyed by the exact Django Group name (matches apps.core.access.ROLE_PRIORITY).
Pure static content -- no database model, edit this file to change wording.
"""

ICON_OVERRIDES = {
    "Sales Manager": "fa-people-arrows",
    "Quotation Staff": "fa-file-invoice-dollar",
    "Admin Staff": "fa-user-tie",
    "Production Manager": "fa-industry",
    "Quality Control": "fa-magnifying-glass",
}


def guide_icon(role_label):
    from apps.core.demo_data import DEMO_ICONS

    return ICON_OVERRIDES.get(role_label) or DEMO_ICONS.get(role_label) or "fa-user-gear"


GUIDES = {
    "Super Admin": {
        "title": "Super Admin",
        "mission": "Full technical ownership of the system — every screen, every setting, every account. "
                    "You're the one people come to when something needs fixing or configuring.",
        "sections": [
            {"nav_section": "people", "title": "People", "features": [
                {"label": "Employees", "url_name": "accounts:employee_list",
                 "description": "Create, edit, or deactivate any staff account and set their role."},
            ]},
            {"nav_section": "settings", "title": "Settings", "features": [
                {"label": "Admin Settings", "url_name": "core:settings_hub",
                 "description": "Company profile, master data (lead sources, statuses, product options), numbering, and templates."},
            ]},
            {"nav_section": "insights", "title": "Insights", "features": [
                {"label": "Reports", "url_name": "reports:index",
                 "description": "Every report in the system, unfiltered."},
            ]},
        ],
        "flow": [
            {"step": "Set up new staff", "detail": "Create their account under Employees and assign the correct role — this is what determines everything they can see."},
            {"step": "Keep master data current", "detail": "Lead sources, statuses, product options, payment terms, and checklists all live under Settings."},
            {"step": "Step in anywhere", "detail": "You can open, edit, or approve any record in the system — useful for covering someone's absence or fixing a mistake."},
            {"step": "Watch the whole business", "detail": "Every notification that any team lead gets, you also get — use the bell icon as an early-warning system."},
        ],
        "tips": [
            "Every one of the demo/quick-login accounts and role guides is visible to you — use the role switcher above to see what any team's day looks like.",
            "The Django Admin (linked under Settings) gives you direct table-level access for anything not covered by a normal screen.",
        ],
    },
    "Management": {
        "title": "Management",
        "mission": "A single view of how the whole business is performing today — sales, production, "
                    "dispatch, installations, and service — without having to ask each team separately.",
        "sections": [
            {"nav_section": "crm_sales", "title": "CRM & Sales", "features": [
                {"label": "Leads", "url_name": "crm:lead_list", "description": "Every lead, across every salesperson."},
                {"label": "Orders", "url_name": "sales:order_list", "description": "Every confirmed order and its value."},
            ]},
            {"nav_section": "insights", "title": "Insights", "features": [
                {"label": "Reports", "url_name": "reports:index",
                 "description": "Monthly sales, lost-business breakdown, production summary, customer list — all downloadable."},
            ]},
            {"nav_section": "people", "title": "People", "features": [
                {"label": "Employees", "url_name": "accounts:employee_list", "description": "See who's on each team."},
            ]},
        ],
        "flow": [
            {"step": "Start on your Dashboard", "detail": "Total leads, conversion rate, today's and this month's sales, the production/dispatch/installation backlog, and a 6-month sales chart — all in one place."},
            {"step": "Open any order for its full story", "detail": "Who sold it, what it quoted at, how much has been paid, how far along manufacturing is, and whether it's delivered — without visiting five screens."},
            {"step": "Get notified on the moments that matter", "detail": "A lead being marked Lost reaches you directly, so you always know why business slips away, not just that it did."},
            {"step": "Pull a report when you need the detail", "detail": "Reports gives you downloadable spreadsheets for board meetings or deeper analysis."},
        ],
        "tips": [
            "You see the same information every team lead sees, plus the roll-up numbers — you don't need a separate summary from anyone.",
            "Lost-lead notifications include the reason recorded, so you can spot a pattern (price, competitor, delivery) early.",
        ],
    },
    "Sales Manager": {
        "title": "Sales Manager",
        "mission": "Oversee the sales team's leads and pipeline, and step in on measurement scheduling when "
                    "a salesperson needs support.",
        "sections": [
            {"nav_section": "crm_sales", "title": "CRM & Sales", "features": [
                {"label": "Leads", "url_name": "crm:lead_list", "description": "All leads across the sales team."},
                {"label": "Sales Pipeline", "url_name": "crm:lead_pipeline", "description": "A board view of every lead by stage."},
            ]},
            {"nav_section": "measurement", "title": "Measurement", "features": [
                {"label": "Rough Measurement", "url_name": "measurement:request_list",
                 "description": "Visibility into measurement jobs feeding your team's quotations."},
            ]},
            {"nav_section": "insights", "title": "Insights", "features": [
                {"label": "Reports", "url_name": "reports:index", "description": "Sales performance by person, and lost-business analysis."},
            ]},
        ],
        "flow": [
            {"step": "Watch the pipeline", "detail": "The Sales Pipeline board shows every lead by stage — spot ones stuck too long in one place."},
            {"step": "Reassign when needed", "detail": "If a salesperson is overloaded or on leave, reassign their leads from the Lead page."},
            {"step": "Get the lost-business picture", "detail": "You're notified whenever a lead is marked Lost, with the reason — use it to coach the team."},
            {"step": "Review performance", "detail": "Reports breaks down sales by salesperson and by month."},
        ],
        "tips": [
            "You see everything an individual Salesperson sees, plus visibility across the whole team — no separate rollup needed.",
        ],
    },
    "Salesperson": {
        "title": "Salesperson",
        "mission": "Own a customer relationship from the very first enquiry through to the day the order is "
                    "won or lost — and stay informed at every stage after that.",
        "sections": [
            {"nav_section": "crm_sales", "title": "CRM & Sales", "features": [
                {"label": "Customers", "url_name": "crm:customer_list", "description": "Every customer you've worked with, with their full history."},
                {"label": "Leads", "url_name": "crm:lead_list", "description": "Your assigned leads and their current stage."},
                {"label": "Quotations", "url_name": "sales:quotation_list", "description": "Quotations sent, awaiting reply, or revised."},
                {"label": "Orders", "url_name": "sales:order_list", "description": "Orders you've won and how they're progressing."},
                {"label": "Sales Targets", "url_name": "sales:target_list", "description": "Your monthly target and progress."},
            ]},
            {"nav_section": "measurement", "title": "Measurement", "features": [
                {"label": "Rough Measurement", "url_name": "measurement:request_list",
                 "description": "Requests you've raised and whether they're complete."},
            ]},
        ],
        "flow": [
            {"step": "Log the enquiry", "detail": "Record the customer's details once — name, number, project, what they're after. Nobody types it in again after this.", "handoff_from": None},
            {"step": "Request a measurement", "detail": "One click sends the job to the Measurement Team, who are notified immediately.", "handoff_to": "Measurement Staff"},
            {"step": "Get notified the moment measuring is done", "detail": "Then request a quotation — the office already has the measurements in front of them.", "handoff_from": "Measurement Staff", "handoff_to": "Quotation Staff"},
            {"step": "Follow up", "detail": "Log every call, WhatsApp, or visit against the customer's record, with a reminder date, so nobody is forgotten."},
            {"step": "Mark the outcome", "detail": "Won opens the order form and everything downstream starts automatically. Lost asks for the reason — it feeds straight into management's reports."},
            {"step": "Stay in the loop after the sale", "detail": "You're notified on full payment, dispatch, installation completion, and warranty activation — you never have to chase for status.", "handoff_from": "Dispatch Staff"},
        ],
        "tips": [
            "“Create Quotation” opens the actual quotation form for you to fill in. “Notify Quotation Team” just pings them to prepare it instead — use whichever fits how your team splits the work.",
            "Your Dashboard's “Needs Follow-up” list is your real daily to-do — check it before opening the full lead list.",
        ],
    },
    "Quotation Staff": {
        "title": "Quotation Staff",
        "mission": "Turn a completed rough measurement into a formal, accurate, company-branded quotation.",
        "sections": [
            {"nav_section": "crm_sales", "title": "CRM & Sales", "features": [
                {"label": "Quotations", "url_name": "sales:quotation_list", "description": "Every quotation, at every stage — draft, sent, negotiation, won or lost."},
                {"label": "Leads", "url_name": "crm:lead_list", "description": "Leads waiting on a quotation."},
            ]},
        ],
        "flow": [
            {"step": "New request lands in your queue", "detail": "A salesperson's “Notify Quotation Team” or a completed measurement puts the lead in front of you.", "handoff_from": "Salesperson"},
            {"step": "Price it line by line", "detail": "Use the measurements already on file — window/door dimensions, glass, hardware — to build the quotation."},
            {"step": "Send it", "detail": "This produces a properly formatted, company-branded PDF automatically.", "handoff_to": "Salesperson"},
            {"step": "Revise if the price changes", "detail": "Every version is kept, so there's always a record of what was first offered and what changed."},
        ],
        "tips": [
            "The salesperson is notified automatically the moment you create or revise a quotation — no need to message them separately.",
        ],
    },
    "Measurement Staff": {
        "title": "Measurement Staff",
        "mission": "Visit customer sites to capture precise window and door dimensions — the initial "
                    "pre-quotation survey, and the final pre-production re-check after the order is confirmed.",
        "sections": [
            {"nav_section": "measurement", "title": "Measurement", "features": [
                {"label": "Rough Measurement", "url_name": "measurement:request_list",
                 "description": "Your queue of measurement requests — assigned, scheduled, and completed jobs."},
                {"label": "Final Measurement", "url_name": "measurement:final_list",
                 "description": "Post-order re-measurement jobs, done right before production starts."},
            ]},
        ],
        "flow": [
            {"step": "New request lands in your queue", "detail": "A salesperson requests a site visit; it appears here with the site address and contact already filled in.", "handoff_from": "Salesperson"},
            {"step": "Schedule it", "detail": "Set a date and mark it Scheduled so the customer knows when to expect you."},
            {"step": "Capture every opening on site", "detail": "Record width, height, type, glass and hardware for each window and door, and attach photos straight from your phone."},
            {"step": "Mark it Completed", "detail": "This tells the salesperson the measurements are ready to quote from.", "handoff_to": "Quotation Staff"},
            {"step": "After the order is confirmed: Final Measurement", "detail": "A separate, more precise request appears against the order — re-verify openings before production cuts material."},
            {"step": "Save it for approval", "detail": "A Production Manager (or Admin Staff/Management) signs off before manufacturing can begin.", "handoff_to": "Production Manager"},
        ],
        "tips": [
            "If a site isn't ready, use ‘Revisit Required’ rather than leaving the job open indefinitely.",
            "Final Measurement figures are what production actually cuts to — accuracy here directly prevents rework.",
        ],
    },
    "Admin Staff": {
        "title": "Admin Staff",
        "mission": "The office backbone that turns a won order into manufacturing paperwork, and keeps the "
                    "master data and employee records in good shape.",
        "sections": [
            {"nav_section": "crm_sales", "title": "CRM & Sales", "features": [
                {"label": "Orders", "url_name": "sales:order_list", "description": "Every confirmed order and its Customer Acquisition Form (CAF)."},
            ]},
            {"nav_section": "production", "title": "Production", "features": [
                {"label": "Production Sheets", "url_name": "production:sheet_list",
                 "description": "Sheets waiting to be filled in and submitted for approval."},
            ]},
            {"nav_section": "people", "title": "People", "features": [
                {"label": "Employees", "url_name": "accounts:employee_list", "description": "Create and manage staff accounts."},
            ]},
            {"nav_section": "settings", "title": "Settings", "features": [
                {"label": "Admin Settings", "url_name": "core:settings_hub", "description": "Master data used across the whole system."},
            ]},
        ],
        "flow": [
            {"step": "An order is confirmed", "detail": "The Customer Acquisition Form (CAF) — the official record used to start manufacturing — fills itself in from everything already on file. You're notified it's ready to review.", "handoff_from": "Salesperson"},
            {"step": "Final measurement gets approved", "detail": "A production sheet stub appears in your queue, ready to fill in.", "handoff_from": "Measurement Staff"},
            {"step": "Fill in the production sheet", "detail": "List exactly what's being manufactured, then submit it for approval.", "handoff_to": "Production Manager"},
            {"step": "Keep master data current", "detail": "Lead sources, product options, payment terms, and checklists all live under Settings."},
        ],
        "tips": [
            "You see the same nine sections a Super Admin does — use that reach to help any team that's stuck, not just your own queue.",
        ],
    },
    "Production Manager": {
        "title": "Production Manager",
        "mission": "Approve production sheets to start manufacturing, and keep the factory floor and dispatch "
                    "backlog moving.",
        "sections": [
            {"nav_section": "production", "title": "Production", "features": [
                {"label": "Production Sheets", "url_name": "production:sheet_list", "description": "Sheets awaiting your approval, and ones in progress."},
                {"label": "Quality Control", "url_name": "production:qc_list", "description": "Every quality check across the floor."},
            ]},
            {"nav_section": "dispatch", "title": "Logistics", "features": [
                {"label": "Dispatch", "url_name": "logistics:dispatch_list", "description": "Orders ready to leave the factory."},
            ]},
            {"nav_section": "insights", "title": "Insights", "features": [
                {"label": "Reports", "url_name": "reports:index", "description": "Production throughput and backlog."},
            ]},
        ],
        "flow": [
            {"step": "A production sheet is submitted", "detail": "Admin Staff fills in and submits a sheet — you're notified it needs approval.", "handoff_from": "Admin Staff"},
            {"step": "Approve it", "detail": "This officially starts manufacturing and creates all sixteen production stages, ready to assign to the floor.", "handoff_to": "Production Staff"},
            {"step": "Step in on QC rework", "detail": "If Quality Control flags a rework and there's no one already assigned to that stage, it comes to you to assign."},
            {"step": "Keep an eye on the whole pipeline", "detail": "Production Sheets, Quality Control, and Dispatch together show you exactly where every order on the floor stands."},
        ],
        "tips": [
            "You can also approve a Final Measurement directly (the same permission Admin Staff and Management have) — useful if Admin Staff is unavailable.",
        ],
    },
    "Production Staff": {
        "title": "Production Staff",
        "mission": "Build the windows and doors, stage by stage, once a production sheet is approved.",
        "sections": [
            {"nav_section": "production", "title": "Production", "features": [
                {"label": "Production Sheets", "url_name": "production:sheet_list", "description": "Sheets with stages assigned to you."},
            ]},
        ],
        "flow": [
            {"step": "A stage gets assigned to you", "detail": "Cutting, welding, hardware fitting, glass fitting — whichever stage you're doing — you're notified the moment it's yours.", "handoff_from": "Production Manager"},
            {"step": "Mark it as you go", "detail": "Started, in progress, completed — so anyone can see exactly where an order sits on the floor without walking over to ask."},
            {"step": "The order moves itself forward", "detail": "Once every stage is finished, it goes to Quality Control automatically — you don't need to remember to send it on.", "handoff_to": "Quality Control"},
        ],
        "tips": [
            "Your Dashboard's “My Open Tasks” list is exactly the stages assigned to you, sorted so anything overdue shows first.",
        ],
    },
    "Quality Control": {
        "title": "Quality Control",
        "mission": "Give every finished order an independent, second set of eyes before it's allowed to ship.",
        "sections": [
            {"nav_section": "production", "title": "Production", "features": [
                {"label": "Quality Control", "url_name": "production:qc_list", "description": "Orders waiting on a quality check."},
            ]},
        ],
        "flow": [
            {"step": "A sheet finishes production", "detail": "All sixteen stages complete — a quality check is created automatically and you're notified.", "handoff_from": "Production Staff"},
            {"step": "Work through the checklist", "detail": "Dimensions, profile, colour, glass, hardware, locking, finish — against the actual finished piece."},
            {"step": "Approve or flag for rework", "detail": "Approving sends it straight to Dispatch. Flagging sends it back to the floor with a note on what needs fixing.", "handoff_to": "Dispatch Staff"},
        ],
        "tips": [
            "Quality approval is deliberately kept separate from Production Staff's own stage sign-offs — you're the independent check, not a rubber stamp.",
        ],
    },
    "Dispatch Staff": {
        "title": "Dispatch Staff",
        "mission": "Get quality-approved orders safely loaded and on their way to the customer's site.",
        "sections": [
            {"nav_section": "dispatch", "title": "Logistics", "features": [
                {"label": "Dispatch", "url_name": "logistics:dispatch_list", "description": "Orders that have passed quality and are ready to leave."},
            ]},
        ],
        "flow": [
            {"step": "Quality Control approves an order", "detail": "It appears in your queue automatically.", "handoff_from": "Quality Control"},
            {"step": "Record the delivery details", "detail": "Vehicle, driver, number of packages, delivery address — then print a delivery note straight from the order."},
            {"step": "Mark it dispatched", "detail": "This notifies the salesperson it's on its way, and automatically creates the installation job.", "handoff_to": "Installation Team"},
        ],
        "tips": [
            "The customer's delivery address is pulled from the order automatically — double-check it before dispatching, since it also becomes the installation team's site address.",
        ],
    },
    "Installation Team": {
        "title": "Installation Team",
        "mission": "Fit the windows and doors on site, and get the customer signed off with a handover certificate.",
        "sections": [
            {"nav_section": "installation", "title": "Logistics", "features": [
                {"label": "Installation", "url_name": "logistics:installation_list", "description": "Jobs scheduled, in progress, or awaiting your attention."},
            ]},
        ],
        "flow": [
            {"step": "A delivery arrives", "detail": "The job appears in your queue automatically — schedule the visit with a team leader and date.", "handoff_from": "Dispatch Staff"},
            {"step": "If the site isn't ready", "detail": "Log the reason on the spot — civil work, flooring, electrical not finished. The salesperson is told immediately instead of finding out only after you've driven there.", "handoff_to": "Salesperson"},
            {"step": "Upload site photos", "detail": "Before, during, and after — straight from your phone on site."},
            {"step": "Capture the customer's signature", "detail": "Once fitting is complete, this produces a signed handover certificate on the spot and starts the warranty automatically.", "handoff_to": "Service/Maintenance Staff"},
        ],
        "tips": [
            "The whole system works from a phone browser — you're expected to use it that way on site, including the camera for photos.",
        ],
    },
    "Service/Maintenance Staff": {
        "title": "Service/Maintenance Staff",
        "mission": "Handle after-sales complaints and warranty service, and keep a full history against every customer.",
        "sections": [
            {"nav_section": "aftersales", "title": "After Sales", "features": [
                {"label": "Service Requests", "url_name": "aftersales:complaint_list", "description": "Complaints assigned to you, open or resolved."},
                {"label": "Warranty", "url_name": "aftersales:warranty_list", "description": "Active and expired warranties by customer."},
            ]},
        ],
        "flow": [
            {"step": "A complaint comes in", "detail": "Logged against the right customer and order, with what's wrong, how urgent it is, and whether it's under warranty.", "handoff_from": "Installation Team"},
            {"step": "It's assigned to you", "detail": "You're notified the moment a complaint lands in your name."},
            {"step": "Visit and resolve it", "detail": "Record what was done, parts used, and any charge, then close it out."},
            {"step": "The history stays attached", "detail": "The full service history stays with that customer for good — the next call starts with the full picture instead of from scratch.", "handoff_to": "Salesperson"},
        ],
        "tips": [
            "Warranty start dates are set automatically the moment installation is handed over — you don't need to calculate them by hand.",
        ],
    },
    "Accounts Staff": {
        "title": "Accounts Staff",
        "mission": "Chase down payment on every order that's still owed money, from invoicing through to final collection.",
        "sections": [
            {"nav_section": "payments", "title": "Accounts", "features": [
                {"label": "Payments", "url_name": "sales:payment_dashboard",
                 "description": "Every order with a balance due, split into not-yet-invoiced and invoiced-but-unpaid."},
            ]},
        ],
        "flow": [
            {"step": "An order still owes money", "detail": "It shows up automatically on your Payments dashboard — nothing to search for.", "handoff_from": "Salesperson"},
            {"step": "Send the invoice", "detail": "Once you've invoiced the customer, mark the order Invoiced — this moves it into the “awaiting payment” list and is what tells you to start following up."},
            {"step": "Follow up until it's paid", "detail": "The order keeps showing up on your dashboard, oldest first, until a payment brings the balance to zero — payments themselves are recorded on the order's own page."},
        ],
        "tips": [
            "The balance due updates automatically the moment anyone records a payment against an order — you're always looking at the real number, not a snapshot.",
        ],
    },
}
