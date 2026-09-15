from apps.core.exports import register_excel, timestamp_suffix, workbook_response


@register_excel("productionsheet")
def export_production_sheet(sheet):
    headers = ["Window/Door #", "Qty", "Width", "Height", "Profile", "Colour", "Glass", "Hardware", "Opening", "Specs"]
    rows = [
        [
            i.window_door_number, i.quantity, str(i.width or ""), str(i.height or ""), i.profile, i.colour,
            i.glass, i.hardware, i.opening_direction, i.manufacturing_specs,
        ]
        for i in sheet.items.all()
    ]
    return workbook_response(headers, rows, filename=f"ProductionSheet_{sheet.production_number}_{timestamp_suffix()}.xlsx", sheet_title="Production Sheet")
