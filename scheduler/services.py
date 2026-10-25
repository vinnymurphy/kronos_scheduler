import json
from datetime import datetime, time
from decimal import Decimal

from django.db import transaction

from .models import ScheduleImport, Shift, ShiftSegment


def parse_time_str(time_str: str) -> time:
    """Converts strings like '08:00 AM' or '02:30 PM' into a
    datetime.time object."""
    return datetime.strptime(time_str.strip(), "%I:%M %p").time()


@transaction.atomic
def import_schedule_json(user, json_data_or_string):
    """Ingests Kronos schedule data (either as a dict or JSON string),

    logs the import history, deactivates older overlapping shifts,
    and creates new active shift and segment records.
    """
    if isinstance(json_data_or_string, str):
        data = json.loads(json_data_or_string)
        raw_text_storage = json_data_or_string
    else:
        data = json_data_or_string
        raw_text_storage = json.dumps(data, indent=2)

    schedule_period = data.get("schedule_period", "")

    # 1. Create the immutable import audit log
    import_record = ScheduleImport.objects.create(
        uploaded_by=user,
        raw_text=raw_text_storage,
        schedule_period=schedule_period,
    )

    shifts_list = data.get("shifts", [])
    incoming_dates = []

    # Validate and extract dates first
    for shift_item in shifts_list:
        date_obj = datetime.strptime(shift_item["date"], "%Y-%m-%d").date()
        incoming_dates.append(date_obj)

    # 2. Version Control: Deactivate any existing active shifts for
    # these dates
    # This ensures your active calendar view only shows the latest
    # updated schedule while past uploads remain saved in
    # ScheduleImport for audit history.
    Shift.objects.filter(date__in=incoming_dates, is_active=True).update(
        is_active=False
    )

    # 3. Create the new active shifts and child segments
    for shift_item in shifts_list:
        shift_date = datetime.strptime(shift_item["date"], "%Y-%m-%d").date()

        shift = Shift.objects.create(
            schedule_import=import_record,
            date=shift_date,
            day_of_week=shift_item["day_of_week"],
            total_hours=Decimal(str(shift_item["total_hours"])),
            is_active=True,
        )

        for seg in shift_item["segments"]:
            ShiftSegment.objects.create(
                shift=shift,
                segment_type=seg["type"],
                start_time=parse_time_str(seg["start"]),
                end_time=parse_time_str(seg["end"]),
                hours=Decimal(str(seg["hours"])),
            )

    return import_record
