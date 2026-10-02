"""The month's reports: an Excel sheet for everyone, and a PDF for one employee.

Both are drawn the moment someone asks and handed straight over as a download.
Nothing is written to storage, so there is nothing to clear up afterwards;
asking again draws them again.
"""

from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from apps.crm import statements

from . import months
from .models import Attendance

NAVY = "192265"
GOLD = "D4AF37"
MONEY = '#,##,##0.00'

COLUMNS = [
    ("S.No", 6), ("Name", 24), ("Designation", 16), ("Monthly salary", 14),
    ("Days present", 10), ("Half days", 9), ("Days absent", 10), ("Holidays", 9), ("Not marked", 10),
    ("Days worked", 10), ("Overtime hours", 11), ("Overtime days (dates)", 26),
    ("Previous advance", 14), ("Advance received this month", 15), ("Deducted this month", 14),
    ("Total advance remaining", 15), ("Salary to be paid", 14),
]
MONEY_COLUMNS = {4, 13, 14, 15, 16, 17}


def _download(content, content_type, filename):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = content_disposition_header(True, filename)
    response["Cache-Control"] = "no-store"
    return response


def month_workbook(month):
    """Everyone's month in one sheet: attendance, overtime, and the advance table."""
    book = Workbook()
    sheet = book.active
    sheet.title = f"{month:%b %Y}"
    width = len(COLUMNS)

    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    sheet["A1"] = f"TITANS WINDOWS — Attendance & Advances, {month:%B %Y}"
    sheet["A1"].font = Font(bold=True, size=14, color=NAVY)
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=width)
    sheet["A2"] = f"{month:%d %b} to {months.last_day(month):%d %b %Y} · drawn {timezone.localtime():%d %b %Y, %I:%M %p}"
    sheet["A2"].font = Font(italic=True, size=9, color="6B7280")

    header_row = 4
    thin = Side(style="thin", color="D7DBE6")
    for column, (title, size) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=header_row, column=column, value=title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = Border(bottom=Side(style="medium", color=GOLD))
        sheet.column_dimensions[get_column_letter(column)].width = size
    sheet.row_dimensions[header_row].height = 32

    totals = [0] * (width + 1)
    row = header_row
    for number, worker in enumerate(months.workers_for(month), start=1):
        found = months.figures(worker, month)
        values = [
            number, worker.name, worker.designation, worker.monthly_salary,
            found.present, found.half, found.absent, found.holiday, found.unmarked,
            found.days_worked, found.overtime_hours, found.overtime_dates or "—",
            found.advance.previous, found.advance.received, found.advance.deducted, found.advance.remaining,
            found.advance.salary_to_pay,
        ]
        row += 1
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            cell.border = Border(bottom=thin)
            if column in MONEY_COLUMNS:
                cell.number_format = MONEY
            if column >= 5 and column != 12:
                cell.alignment = Alignment(horizontal="right")
            if column >= 4 and column != 12:
                totals[column] += value or 0
        if number % 2 == 0:
            for column in range(1, width + 1):
                sheet.cell(row=row, column=column).fill = PatternFill("solid", fgColor="F2F4F9")

    row += 1
    sheet.cell(row=row, column=2, value="Total").font = Font(bold=True)
    for column in list(range(4, 12)) + list(range(13, width + 1)):
        cell = sheet.cell(row=row, column=column, value=totals[column])
        cell.font = Font(bold=True)
        cell.border = Border(top=Side(style="medium", color=NAVY))
        if column in MONEY_COLUMNS:
            cell.number_format = MONEY
    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=3)
    sheet.cell(row=row + 2, column=1, value=(
        "Days worked = days present + half of each half day. Previous advance is what was still owed coming "
        "into the month. Remaining = previous + received this month − deducted. Salary to be paid = monthly "
        "salary − deducted (the deduction is entered when each employee's report is downloaded)."
    )).font = Font(italic=True, size=9, color="6B7280")

    output = BytesIO()
    book.save(output)
    return _download(
        output.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        f"Attendance-{month:%Y-%m}.xlsx",
    )


# ---------------------------------------------------------------- one employee's PDF
CODES = {
    Attendance.Status.PRESENT: ("P", colors.HexColor("#dcfce7")),
    Attendance.Status.ABSENT: ("A", colors.HexColor("#fee2e2")),
    Attendance.Status.HALF: ("½", colors.HexColor("#fef3c7")),
    Attendance.Status.HOLIDAY: ("H", colors.HexColor("#e0e7ff")),
}


def employee_pdf(worker, month, to_date=None):
    """One employee's month, laid out to be read or printed.

    `to_date` makes it the month so far — the report the employee's page can
    always give, with whatever has been recorded up to that day.
    """
    style = statements._styles()
    found = months.figures(worker, month)
    period = f"{month:%B %Y}" if to_date is None else f"1 – {to_date:%d %B %Y} (month in progress)"
    story = [
        Paragraph(escape(worker.name), style["title"]),
        Paragraph(escape(f"{worker.designation + ' · ' if worker.designation else ''}{period}"), style["sub"]),
        Spacer(1, 6 * mm),
    ]
    facts = [
        ("Mobile", worker.phone or "—"),
        ("Joined", f"{worker.joined_on:%d %b %Y}" if worker.joined_on else "—"),
        ("Monthly salary", statements.money(worker.monthly_salary)),
        ("Report for", f"{month:%B %Y}" if to_date is None else f"{month:%B %Y}, up to {to_date:%d %b}"),
    ]
    story += [statements._facts_table(facts, style), Spacer(1, 6 * mm)]

    story.append(Paragraph("<b>Attendance</b>", style["cell"]))
    story.append(Spacer(1, 2 * mm))
    summary = [
        [Paragraph(label, style["head"]) for label in ["Present", "Half days", "Absent", "Holidays", "Not marked", "Days worked", "Overtime hours"]],
        [Paragraph(str(value), style["cell"]) for value in [
            found.present, found.half, found.absent, found.holiday, found.unmarked, f"{found.days_worked:g}", f"{found.overtime_hours:g}",
        ]],
    ]
    story.append(statements._grid(summary, [24.8 * mm] * 7, style, right_from=7))
    story.append(Spacer(1, 5 * mm))

    # The month as a calendar: each day's mark, and its overtime.
    story.append(Paragraph("<b>Day by day</b>", style["cell"]))
    story.append(Spacer(1, 2 * mm))
    grid = [[Paragraph(day, style["head"]) for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]]]
    shading = []
    for r, week in enumerate(months.calendar_weeks(month, found.days, found.advances_by_day), start=1):
        cells = []
        for c, (day, record, given) in enumerate(week):
            if day is None:
                cells.append("")
                continue
            mark = ""
            if record:
                code, fill = CODES[record.status]
                mark = f"<br/><b>{code}</b>"
                if record.overtime_hours:
                    mark += f" <font size='7' color='#192265'>+{record.overtime_hours:g}h OT</font>"
                shading.append(("BACKGROUND", (c, r), (c, r), fill))
            if given:
                mark += f"<br/><font size='7' color='#0f766e'>Adv {statements.money(given, prefix=False)}</font>"
            cells.append(Paragraph(f"{day.day}{mark}", style["cell"]))
        grid.append(cells)
    table = Table(grid, colWidths=[24.8 * mm] * 7, rowHeights=[None] + [13 * mm] * (len(grid) - 1), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), statements.NAVY),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, statements.GOLD),
        ("GRID", (0, 1), (-1, -1), 0.4, colors.HexColor("#d7dbe6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        *shading,
    ]))
    story.append(table)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("P present · ½ half day · A absent · H holiday · OT overtime hours", style["note"]))
    story.append(Spacer(1, 5 * mm))

    if found.overtime_days:
        story.append(Paragraph("<b>Overtime</b>", style["cell"]))
        story.append(Spacer(1, 2 * mm))
        rows = [[Paragraph("Date", style["head"]), Paragraph("Hours", style["headr"])]]
        rows += [[Paragraph(f"{day:%a, %d %b %Y}", style["cell"]), Paragraph(f"{hours:g}", style["cellr"])] for day, hours in found.overtime_days]
        rows.append([Paragraph("<b>Total</b>", style["cell"]), Paragraph(f"<b>{found.overtime_hours:g}</b>", style["cellr"])])
        story.append(statements._grid(rows, [60 * mm, 30 * mm], style, right_from=1))
        story.append(Spacer(1, 5 * mm))

    advance = found.advance
    if advance.given:
        story.append(Paragraph("<b>Advances given this month</b>", style["cell"]))
        story.append(Spacer(1, 2 * mm))
        rows = [[Paragraph("Date", style["head"]), Paragraph("Amount", style["headr"])]]
        rows += [[Paragraph(f"{day:%a, %d %b %Y}", style["cell"]), Paragraph(statements.money(amount), style["cellr"])]
                 for day, amount in advance.given]
        rows.append([Paragraph("<b>Total</b>", style["cell"]), Paragraph(f"<b>{statements.money(advance.received)}</b>", style["cellr"])])
        story.append(statements._grid(rows, [60 * mm, 40 * mm], style, right_from=1))
        story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("<b>Advance</b>", style["cell"]))
    story.append(Spacer(1, 2 * mm))
    rows = [
        [Paragraph(label, style["headr"]) for label in
         ["Previous advance", "Advance received this month", "Deducted this month", "Total advance remaining"]],
        [Paragraph(statements.money(value), style["cellr"]) for value in
         [advance.previous, advance.received, advance.deducted, advance.remaining]],
    ]
    story.append(statements._grid(rows, [43.4 * mm] * 4, style, right_from=0))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Previous advance is what was still owed coming into the month. "
        "Remaining = previous + received this month − deducted.",
        style["note"],
    ))
    story.append(Spacer(1, 5 * mm))

    # What they are paid this month: the salary, less what is taken back towards the advance.
    story.append(Paragraph("<b>Salary</b>", style["cell"]))
    story.append(Spacer(1, 2 * mm))
    pay = Table(
        [[Paragraph(label, style["cell"]), Paragraph(value, style["cellr"])] for label, value in [
            ("Monthly salary", statements.money(advance.salary)),
            ("Less: deducted towards the advance",
             statements.money(advance.deducted) if advance.settled or to_date is None else "at the month's end"),
            ("<b>Salary to be paid</b>", f"<b>{statements.money(advance.salary_to_pay)}</b>"),
        ]],
        colWidths=[70 * mm, 40 * mm], hAlign="LEFT",
    )
    pay.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, statements.NAVY),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, statements.NAVY),
        ("BACKGROUND", (0, -1), (-1, -1), statements.BAND),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(pay)

    if to_date is not None:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            f"Figures up to {to_date:%d %b %Y}. The month is still open, so they may change; the amount to deduct is "
            "entered when the month's report is downloaded after it closes.", style["note"]))
    suffix = f"{month:%Y-%m}" if to_date is None else f"{to_date:%Y-%m-%d}"
    filename = f"Report-{statements._filename(worker.name)}-{suffix}.pdf"
    buffer, doc = statements._document(filename)
    return statements._respond(buffer, doc, story, filename, decorate=statements.letterhead("Monthly Attendance Report"))
