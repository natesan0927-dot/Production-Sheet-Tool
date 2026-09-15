from apps.core.exports import register_excel, timestamp_suffix, workbook_response


@register_excel("measurementrequest")
def export_measurement(measurement):
    headers = ["Window No.", "Room", "Width", "Height", "Qty", "Type", "Glass", "Profile", "Hardware", "Remarks"]
    rows = [
        [
            i.window_number, i.room_location, str(i.width), str(i.height), i.quantity,
            i.window_type or i.door_type, str(i.glass_type or ""), str(i.profile_series or ""),
            str(i.hardware or ""), i.remarks,
        ]
        for i in measurement.items.all()
    ]
    return workbook_response(headers, rows, filename=f"Measurement_{measurement.measurement_id}_{timestamp_suffix()}.xlsx", sheet_title="Measurement")


@register_excel("finalmeasurementrequest")
def export_final_measurement(fm):
    headers = ["Window No.", "Width", "Height", "Opening", "Frame", "Glass", "Hardware", "Colour", "Remarks"]
    rows = [
        [i.window_number, str(i.final_width), str(i.final_height), i.opening_direction, i.frame_details, i.glass_details, i.hardware_details, i.colour, i.remarks]
        for i in fm.items.all()
    ]
    return workbook_response(headers, rows, filename=f"FinalMeasurement_{fm.final_measurement_id}_{timestamp_suffix()}.xlsx", sheet_title="Final Measurement")
