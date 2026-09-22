# Open questions on the rebuild

Built from `TITANS-REFURBISHED.pdf` and `Titans Windows Warranty Certificate (1).pdf`.
Where the spec did not say, I picked something and kept going. Items marked **Decided**
have since been settled by you; the rest are still open.

## 1. Who uploads quotations?

**Decided — Quotation Staff is its own role.** They have their own login and a *Quotation
Upload* tab listing the customers whose measurements are in. The Accounts Department no longer
uploads quotations; they keep *Confirmed Orders*, the financial side.


## 2. Financial details sent to accounts

"Send the financial details alone of this particular customer to the accounts team" is built
as a notification plus the *Confirmed Orders* tab showing: customer, site, quotation number,
order value, advance received, balance, committed delivery date, salesperson.
**Tell me if any field should be added or removed.**

## 3. The "Negotiation" column in the Sales Pipeline

**Decided — removed.** The Negotiation column and the flag behind it are gone. The pipeline
now reads Quotation Pending → Quotation Sent → Follow-up → Won → Lost.


## 4. Dropdown options I had to invent

**Decided.**

- **Site stage:** Not Started, Foundation, Brick Work, Plastering, Ready for Installation
  (Painting removed).
- **Lead source:** Walk-in, Reference, Website, Meta, McCoyMart, IndiaMART, TradeIndia,
  JustDial, Google, BNI, Others. Picking **Others** reveals a text box, and the lead will not
  save until it is filled in.
- **Approx quantity** is still a plain number. Say the word if you want free text.


## 5. "To do for the day"

**Decided — split into three separate things.**

- **Today's lead follow-up** — salesperson only, on the dashboard: strictly today's follow-ups.
- **My to-do** — a To-Do tab every role has, showing the tasks assigned to that person and
  who assigned each one.
- **Assign a to-do** — on the same tab: pick any person from a dropdown, give it a title and a
  due date, and it appears on their to-do list. What you assign to others shows under
  "Waiting on others" until they tick it off.


## 6. The warranty certificate has spelling mistakes

**Resolved a different way.** The system no longer redraws either document. It now opens your
actual `Order confirmation approval form.pdf` and `Titans Windows Warranty Certificate.pdf`
and types the lead's details onto the blank lines, so what prints is your own stationery,
wording and artwork exactly as supplied — spellings included.

That also retires the earlier question about missing artwork: the PROMINANCE logo, the 10-year
seal and the gold banner are all in your originals, so they come through untouched.


## 7. Artwork I don't have files for

**No longer an issue** — see 6. Both documents are now your original PDFs, so every piece of
artwork is already in them.


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

**Decided — "Need Revision", not reject.** The measurement staff can approve the sheet or send
it back. Sending it back requires written remarks; the request is refused if the box is empty.
The remarks then sit at the top of the production stage for the production team, who upload a
corrected sheet.


## 11. Site Fabrication asks for the order value again

**Decided.** The salesperson now enters the window count and total site sq ft when marking the
order won, and the Future Production column simply displays those along with the confirmed
order value. The production staff no longer retype anything.


## 12. Who can edit a lead after it is saved?

**Decided.** Both the salesperson and the Super Admin can edit a lead, from the three-dot menu
on each row of the Leads tab (which also offers delete, with a confirmation). A salesperson can
only touch their own leads; the Super Admin can also reassign a lead to a different salesperson.


## 13. Uploaded files are not behind the login

Anything uploaded (quotations, signed CAFs, measurements, warranty certificates) is served
straight from `/media/...`, so **anyone who has the link can open it without signing in** —
they just can't discover the link without access. That is how the old build worked too, and
it keeps things simple. If you'd rather every download went through a login check, it's a
contained change; tell me and I'll do it.

## 14. Things to know about the rebuild

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
