# Open questions on the rebuild

Built from `TITANS-REFURBISHED.pdf` and `Titans Windows Warranty Certificate (1).pdf`.
Where the spec did not say, I picked the option in **bold** and kept going. Each one is
a small change if you want it the other way.

## 1. Who uploads quotations?

The roles list has six roles and no "quotation staff", but the Quotation stage says it is
"accessible only by the superadmin and quotation staff". The spec also never lists the tabs
for the Accounts Department.

**I made the Accounts Department the quotation team.** Their two tabs are *Quotations*
(leads whose measurements are in and are waiting for a quotation) and *Confirmed Orders*
(the financial details, which the spec says to send to accounts once a lead is won).

If quotation staff are meant to be a separate, seventh role, say so and I'll split them.

## 2. Financial details sent to accounts

"Send the financial details alone of this particular customer to the accounts team" is built
as a notification plus the *Confirmed Orders* tab showing: customer, site, quotation number,
order value, advance received, balance, committed delivery date, salesperson.
**Tell me if any field should be added or removed.**

## 3. The "Negotiation" column in the Sales Pipeline

The pipeline needs a Negotiation column, but nothing in the stage flow ever sets that state.
**I added a "Mark as In Negotiation" toggle** on the Follow-up / Won-Lost stage, so the
salesperson decides. The alternative is to infer it (say, two or more follow-ups logged).

Related: I split *Quotation Sent* from *Follow-up* by whether any follow-up has been
scheduled for the lead yet. Tell me if you meant a different split.

## 4. Dropdown options I had to invent

- **Site stage:** Not Started, Foundation, Brick Work, Plastering, Painting, Ready for Installation
- **Lead source:** Walk-in, Reference, Website, Social Media, Architect / Builder, Exhibition, Other
- **Approx quantity** is a plain number (count of windows/doors). If you want free text like
  "12 windows + 2 doors", that's a one-line change.

Send me your real lists and I'll swap them in.

## 5. "To do for the day"

The dashboard's to-do list shows **today's follow-ups plus any lead sitting on a step that
belongs to the salesperson** (Lead Created, or Won/Lost after the quotation arrives).
There is no separate task-assignment feature anywhere in the spec, so "assigned tasks" is
my reading. If you want the Super Admin to be able to hand out ad-hoc to-dos, that's a
separate feature — tell me and I'll add it.

## 6. The warranty certificate has spelling mistakes

Your certificate reads "HARDWARE **CRETIFICATE** OF GUARANTEE", "IN THE **FEILD**",
"NON **TRANSFRABLE**", "**EXPRESELY** IN WRITTEN". **I reproduced your file exactly**,
mistakes included, rather than silently changing a document you issue to customers.
Say the word and I'll correct them.

## 7. Artwork I don't have files for

Both documents are rebuilt to match your originals, but three pieces of artwork exist only
as pictures inside your PDFs, so I approximated them:

- the **PROMINANCE uPVC Window Systems** logo (on both documents) — drawn as styled text
- the **10 YEAR GUARANTEE** starburst seal (warranty certificate) — drawn as a plain box
- the **gold/navy banner** across the bottom of the CAF pages — left out

Send me PNGs of these three and they'll drop straight in.

## 8. The CAF skips clause 5

Your Order Confirmation form is numbered 1, 2, 3, 4, **6**, 7, 8, 9 — there is no clause 5.
I copied it exactly as it is. **Was clause 5 lost by accident?**

Also: the "Date" at the top is filled with the date the CAF is downloaded. If it should be
the order confirmation date instead, that's a one-line change.

## 9. One file or many?

The spec only says "multiple files upload should be permitted" for quotations, so
**quotations take many files and everything else takes one at a time** (rough measurement,
final measurement, signed CAF, production sheet, signed warranty). Uploading again just adds
another file, it never deletes the old one. Tell me if any of the others need multi-upload.

## 10. Rejecting a production sheet

The spec has the measurement staff approving a production sheet, but says nothing about
rejecting one. **There is no reject button** — the production staff can simply upload a
corrected sheet, which replaces the pending one. If measurement staff need to reject with a
written reason, tell me.

## 11. Site Fabrication asks for the order value again

Column 1 asks the production staff to type in the order value, but the Won stage already
captured it. **I pre-fill it with the confirmed order value and let them change it.**

## 12. Who can edit a lead after it is saved?

The spec says the Super Admin "can view and modify the leads" — so **only the Super Admin
gets an Edit Lead button**, and they can also reassign a lead to a different salesperson.
A salesperson currently cannot correct their own typo. Tell me if they should be able to.

## 13. Things to know about the rebuild

- **The database was reset.** This is a fresh schema; the old data is not carried over. Your
  old dev database file was moved aside rather than deleted, and all the old code is still in
  git history (commit `1dd7293`) if anything needs to be recovered.
- **`docs/Titans Windows Handbook.pdf` is now out of date** — it describes the old system. I
  left it alone. Say the word and I'll rewrite or remove it.
- **The Procfile still runs `seed_data` on every deploy**, which creates the seven demo
  accounts. Good for showing the system; remove that before real customer data goes in.
- Anything the spec did not mention is **not** built — no quality checks, no dispatch
  logistics module, no complaints/service module, no reports module. Those all existed in the
  old build and are gone.
