"""The walkthrough each role gets on their first sign-in.

Two halves. The intro is a short narrated presentation — an avatar talks over a
screenshot of whatever it is describing, one scene at a time. The tour then
walks the person through their own tabs, one page at a time, highlighting the
sidebar link and saying what lives there.

The tour is built from the same navigation the sidebar renders, so it always
covers exactly the tabs that role actually has — including whatever the Super
Admin has widened or narrowed.
"""

from django.urls import reverse

from apps.accounts.models import Role

# A scene is (screenshot name, caption, what the avatar says). The screenshot is
# static/guide/<name>.png; if one is missing the stage just shows the backdrop.
OPENING = (
    "dashboard",
    "One system, from first call to handover",
    "Welcome to Titans Windows. Everything a job goes through lives here — the "
    "first enquiry, the measurements, the quotation, the order, the factory "
    "floor, the dispatch and the handover. One lead, one file, start to finish.",
)

JOURNEY = (
    "journey",
    "Eight steps, one lead",
    "Every lead walks the same eight steps. You always see which step it is on "
    "and who it is waiting for, so nothing quietly stalls. You only work the "
    "steps that belong to your job — the rest are there for context.",
)

CLOSING = (
    "todo",
    "Your to-do list and notifications",
    "Anyone can send you a task, and you will see a pop-up the moment something "
    "needs you. When you are done here I will walk you through your tabs one by "
    "one. You can stop any time, and replay all of this from the Guide tab.",
)


ROLE_INTROS = {
    Role.SALESPERSON: {
        "headline": "Your walkthrough — Salesperson",
        "scenes": [
            OPENING,
            JOURNEY,
            (
                "leads",
                "Every lead starts with you",
                "You add the lead — who they are, where the site is, where it came "
                "from and roughly what it is worth. From there you ask for a rough "
                "measurement, and the job is on its way.",
            ),
            (
                "followups",
                "One follow-up at a time",
                "Each lead carries exactly one open follow-up. Book the next one and "
                "the last is filed into that lead's history. Anything still open sits "
                "on your dashboard until you tick it off, and turns red after six in "
                "the evening on its day.",
            ),
            (
                "targets",
                "Your target, live",
                "Once a quotation is out you mark the lead won or lost. A win counts "
                "straight towards your monthly target, and you can see exactly which "
                "sites got you there.",
            ),
            CLOSING,
        ],
    },
    Role.MEASUREMENT: {
        "headline": "Your walkthrough — Measurement Staff",
        "scenes": [
            OPENING,
            JOURNEY,
            (
                "rough",
                "Rough measurements",
                "When a salesperson asks for a rough measurement the job lands in your "
                "queue with the customer's name, number and site address. Take the "
                "measurements, upload the sheet, and the quotation team is notified.",
            ),
            (
                "caf",
                "The CAF and the final measurement",
                "Once an order is confirmed, download the order confirmation form, get "
                "it signed, and upload it together with the final measurement. Both "
                "have to go up at the same time — that is what opens production.",
            ),
            (
                "validation",
                "You approve the production sheet",
                "Production draws the sheet from your measurements, and you are the one "
                "who checks it. Approve it, or send it back for revision with a note "
                "saying what is wrong.",
            ),
            CLOSING,
        ],
    },
    Role.QUOTATION: {
        "headline": "Your walkthrough — Quotation Staff",
        "scenes": [
            OPENING,
            JOURNEY,
            (
                "quotation",
                "Your queue",
                "As soon as a rough measurement is in, that lead appears in your queue. "
                "You will find the measurement sheet and the site details right there "
                "on the lead.",
            ),
            (
                "quotation",
                "Quotation and elevation together",
                "Type your quotation number, attach the quotation, and attach the "
                "elevation report. Both are required. The elevation goes on to the "
                "measurement team for the final visit.",
            ),
            CLOSING,
        ],
    },
    Role.ACCOUNTS: {
        "headline": "Your walkthrough — Accounts",
        "scenes": [
            OPENING,
            JOURNEY,
            (
                "accounts",
                "Every confirmed order",
                "The moment a salesperson confirms an order, the figures reach you — "
                "order value, advance and balance, with the total outstanding across "
                "every job at the top.",
            ),
            (
                "ledger",
                "A ledger per job",
                "Open any order for its own ledger. Post each payment as it comes in "
                "with a remark and the receipt, and the balance keeps itself up to "
                "date. A job only counts as outstanding once it has been invoiced.",
            ),
            CLOSING,
        ],
    },
    Role.PRODUCTION: {
        "headline": "Your walkthrough — Production",
        "scenes": [
            OPENING,
            JOURNEY,
            (
                "production",
                "The production sheet",
                "When the signed order form and the final measurement are both in, the "
                "job reaches you. Upload the production sheet and the measurement team "
                "checks it — they either approve it or send it back with a note.",
            ),
            (
                "fabrication",
                "The factory floor",
                "Approved jobs move across three columns: future production, under "
                "production, and ready for dispatch. All eight fabrication steps must "
                "be ticked before anything can go to dispatch.",
            ),
            (
                "fabrication",
                "Dispatch",
                "Record who is installing, the invoice number and the invoice date. "
                "That closes your part and opens handover for the field manager.",
            ),
            CLOSING,
        ],
    },
    Role.FIELD_MANAGER: {
        "headline": "Your walkthrough — Field Manager",
        "scenes": [
            OPENING,
            JOURNEY,
            (
                "warranty",
                "Handover",
                "Once a job is dispatched it reaches you. Download the handover "
                "warranty certificate — it comes out already filled in with the "
                "customer's name, the invoice number and the invoice date.",
            ),
            (
                "warranty",
                "Closing the job",
                "Get the certificate signed at site, upload it back, and save the "
                "project. That is the job finished, and it moves to completed projects.",
            ),
            (
                "complaints",
                "Service requests",
                "After handover, any complaint is raised against that project and stays "
                "open until you record what was done to fix it.",
            ),
            CLOSING,
        ],
    },
    Role.SUPER_ADMIN: {
        "headline": "Your walkthrough — Super Admin",
        "scenes": [
            OPENING,
            JOURNEY,
            (
                "leads",
                "Every job, every team",
                "You see every tab every role has, and every lead whoever it belongs "
                "to. You can reassign a lead to a different salesperson, and edit or "
                "remove one outright.",
            ),
            (
                "stage-access",
                "Who sees what",
                "Each role only sees the steps it works on. From Stage Access you can "
                "widen or narrow that for any individual employee.",
            ),
            (
                "targets",
                "Targets and the floor",
                "You are the only one who sets monthly targets. You can also move jobs "
                "between the three fabrication columns yourself when you need to — "
                "normally the teams do that as they work.",
            ),
            CLOSING,
        ],
    },
}


# What each tab is for, in one or two lines. Keyed by the URL name the sidebar
# links to, so a tab that a role does not have simply never comes up.
PAGE_NOTES = {
    "crm:dashboard": (
        "Your day at a glance",
        "Your figures across the top, whatever happened today in the middle, and "
        "your open follow-ups and tasks below. Tick things off as you deal with them.",
    ),
    "crm:lead_list": (
        "Leads",
        "Every lead you own. Search by name, number or location, filter by status, "
        "and use the three dots on a row to open, edit or remove one. Add Lead is "
        "top right.",
    ),
    "crm:pipeline": (
        "Sales Pipeline",
        "The same leads as cards, grouped by where they have got to — quotation "
        "pending, quotation sent, follow-up, won and lost.",
    ),
    "crm:targets": (
        "Sales Target",
        "This month's target against what you have actually won, with the list of "
        "sites that got you there.",
    ),
    "crm:followups": (
        "Follow-up",
        "Every follow-up that is still open, oldest first. Overdue ones are red, "
        "today's are amber. Mark one done here or from the lead itself.",
    ),
    "crm:lost_opportunities": (
        "Lost Opportunities",
        "Leads that did not come off, with the reason and — where you recorded it — "
        "the price the customer got elsewhere.",
    ),
    "crm:completed_projects": (
        "Completed Projects",
        "Finished jobs with all their documents kept together, and whether the "
        "payment has actually cleared.",
    ),
    "crm:queue_rough": (
        "Rough Measurements",
        "Leads waiting on a first measurement. Each one carries the customer's name, "
        "number and site address so you can go straight out.",
    ),
    "crm:queue_final": (
        "Final Measurements",
        "Confirmed orders waiting on the signed order form and the final measurement. "
        "Both have to be uploaded together.",
    ),
    "crm:queue_production_validation": (
        "Production Sheet Validation",
        "Sheets production has drawn up, waiting on your check. Approve, or send back "
        "for revision with a note.",
    ),
    "crm:queue_quotations": (
        "Quotation Upload",
        "Leads that have been measured and are waiting on a price. Quotation and "
        "elevation report both go up here.",
    ),
    "crm:queue_accounts": (
        "Accounts",
        "Every confirmed order with its value, advance and balance, the days each "
        "invoice has been outstanding, and the total across all of them. Open one "
        "for its ledger, where you post payments and add transport or other "
        "charges to the invoice.",
    ),
    "crm:queue_production": (
        "Production",
        "Jobs cleared to start. Upload the production sheet and wait for the "
        "measurement team to approve it.",
    ),
    "crm:queue_fabrication": (
        "Site Fabrication Status",
        "The factory floor, all three columns written out with their figures and "
        "their buttons. A job only reaches dispatch once all eight fabrication "
        "steps are ticked, and anything moved by mistake can be put back.",
    ),
    "crm:queue_warranty": (
        "Warranty & Handover",
        "Dispatched jobs waiting to be handed over. Download the certificate, get it "
        "signed, upload it, save the project.",
    ),
    "crm:complaint_list": (
        "Service Requests",
        "Complaints raised against handed-over projects. They stay open until you "
        "record what was done.",
    ),
    "crm:todo_list": (
        "To-Do",
        "Tasks anyone has sent you, and tasks you have sent others. Whoever assigned "
        "it is told the moment you mark it done.",
    ),
    "crm:day_summary": (
        "Summary for the Day",
        "Everyone on the team with a count of what they got through today. Open "
        "anyone to see their whole day, grouped by the kind of work.",
    ),
    "crm:stage_access_list": (
        "Stage Access",
        "Which steps of the journey each employee can see. Pick anyone and tick the "
        "stages they should have.",
    ),
    "crm:guide": (
        "Guide",
        "This walkthrough lives here. Replay the video, run the tour again, or just "
        "read what each tab does — any time you need it.",
    ),
}


def intro_for(user):
    """The scenes this person's walkthrough plays, as plain dicts for the page."""
    intro = ROLE_INTROS.get(user.role) or ROLE_INTROS[Role.SALESPERSON]
    return {
        "headline": intro["headline"],
        "role_label": user.get_role_display(),
        "scenes": [
            {"shot": shot, "caption": caption, "narration": narration}
            for shot, caption, narration in intro["scenes"]
        ],
    }


def tour_for(nav_groups):
    """One step per tab the sidebar is showing, in the order it shows them."""
    steps = []
    for _section, _accent, items in nav_groups:
        for item in items:
            note = PAGE_NOTES.get(item.get("url_name"))
            if not note:
                continue
            title, body = note
            steps.append({"url": item["url"], "title": title, "body": body})
    return steps


def written_guide(nav_groups):
    """The same notes as a page you can read rather than click through."""
    sections = []
    for section, _accent, items in nav_groups:
        entries = [
            {"label": item["label"], "url": item["url"], "note": PAGE_NOTES[item["url_name"]][1]}
            for item in items
            if item.get("url_name") in PAGE_NOTES
        ]
        if entries:
            sections.append({"section": section, "entries": entries})
    return sections


def guide_url():
    return reverse("crm:guide")
