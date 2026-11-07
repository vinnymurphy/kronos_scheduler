import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

MONTH_HEADER = re.compile(r"^([A-Za-z]+,\s*\d{4})$", re.IGNORECASE)
DATE_HEADER = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)$")
SHIFT_LINE = re.compile(
    r"^(\d{1,2}:\d{2}\s*(?:AM|PM))\s*-\s*"
    r"(\d{1,2}:\d{2}\s*(?:AM|PM))\s*"
    r"\[(\d+(?:\.\d+)?)\](.*)$",
    re.IGNORECASE,
)
APPROVED_LINE = re.compile(r"^Approved\s*\[\d+\]$", re.IGNORECASE)
IN_PROGRESS_LINE = re.compile(r"^In Progress\s*\[\d+\]$", re.IGNORECASE)
PAST_HOURS_LINE = re.compile(
    r"^(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:/(?P<year>\d{4}))?" r"\s+(?P<ranges>.+)$"
)
PAST_HOURS_RANGE = re.compile(
    r"^(?P<start_hour>\d{1,2}):(?P<start_minute>\d{2})\s*"
    r"(?P<start_period>am|pm)?\s*-\s*"
    r"(?P<end_hour>\d{1,2}):(?P<end_minute>\d{2})\s*"
    r"(?P<end_period>am|pm)?$",
    re.IGNORECASE,
)


def parse_kronos_schedule(raw_text: str) -> dict:
    """Convert the Kronos text format into the structure expected by the importer."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    month_positions = [
        index for index, line in enumerate(lines) if MONTH_HEADER.fullmatch(line)
    ]
    if not month_positions:
        raise ValueError("No month and year header found in the Kronos schedule.")

    first_month_index = month_positions[0]
    has_unlabeled_dates = any(
        DATE_HEADER.fullmatch(line) for line in lines[:first_month_index]
    )
    first_month = MONTH_HEADER.fullmatch(lines[first_month_index]).group(1)
    if has_unlabeled_dates:
        first_month = _previous_month_label(first_month)

    current_month = first_month
    current_shift = None
    parsed_shifts = []

    def finish_shift():
        if current_shift is None:
            return

        try:
            shift_date = datetime.strptime(
                f"{current_shift['day']} {current_shift['month']}", "%d %B, %Y"
            ).date()
        except ValueError as error:
            raise ValueError(
                f"Invalid schedule date: {current_shift['day']} "
                f"{current_shift['month']}."
            ) from error

        entries = current_shift["entries"]
        segments = []
        if entries:
            detailed_entries = (
                entries
                if len(entries) == 1 or entries[0]["type"] == "break"
                else entries[1:]
            )
            segments = [
                {
                    "type": entry["type"],
                    "start": entry["start"],
                    "end": entry["end"],
                    "hours": entry["hours"],
                }
                for entry in detailed_entries
            ]

        parsed_shifts.append(
            {
                "date": shift_date.isoformat(),
                "day_of_week": current_shift["weekday"],
                "total_hours": entries[0]["hours"] if entries else 0,
                "segments": segments,
            }
        )

    for line_number, line in enumerate(lines, start=1):
        month_match = MONTH_HEADER.fullmatch(line)
        if month_match:
            current_month = month_match.group(1)
            continue

        date_match = DATE_HEADER.fullmatch(line)
        if date_match:
            finish_shift()
            current_shift = {
                "month": current_month,
                "day": date_match.group(1),
                "weekday": date_match.group(2),
                "entries": [],
            }
            continue

        if (
            line == "-"
            or APPROVED_LINE.fullmatch(line)
            or IN_PROGRESS_LINE.fullmatch(line)
        ):
            continue

        shift_match = SHIFT_LINE.fullmatch(line)
        if shift_match and current_shift is not None:
            try:
                datetime.strptime(shift_match.group(1).strip(), "%I:%M %p")
                datetime.strptime(shift_match.group(2).strip(), "%I:%M %p")
            except ValueError as error:
                raise ValueError(
                    f"Invalid time on line {line_number}: {line}"
                ) from error
            current_shift["entries"].append(
                {
                    "type": (
                        "break" if "break" in shift_match.group(4).lower() else "work"
                    ),
                    "start": shift_match.group(1),
                    "end": shift_match.group(2),
                    "hours": float(shift_match.group(3)),
                }
            )
            continue

        raise ValueError(f"Unrecognized Kronos schedule line {line_number}: {line}")

    finish_shift()
    if not parsed_shifts:
        raise ValueError("No schedule dates found in the Kronos text.")

    first_date = datetime.strptime(parsed_shifts[0]["date"], "%Y-%m-%d")
    last_date = datetime.strptime(parsed_shifts[-1]["date"], "%Y-%m-%d")
    first_label = first_date.strftime("%B, %Y")
    last_label = last_date.strftime("%B, %Y")
    schedule_period = (
        first_label if first_label == last_label else f"{first_label} - {last_label}"
    )
    return {"schedule_period": schedule_period, "shifts": parsed_shifts}


def parse_past_hours(raw_text: str, *, default_year: int) -> list[dict]:
    """Parse dated work intervals, including multiple intervals on one day."""
    shifts_by_date = {}
    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue

        match = PAST_HOURS_LINE.fullmatch(line)
        if match is None:
            raise ValueError(
                f"Invalid entry on line {line_number}. Use M/D followed by "
                "one or more time ranges."
            )

        year = int(match.group("year") or default_year)
        try:
            shift_date = date(year, int(match.group("month")), int(match.group("day")))
        except ValueError as error:
            raise ValueError(f"Invalid date on line {line_number}: {error}.") from error

        intervals = shifts_by_date.setdefault(
            shift_date, {"date": shift_date, "segments": [], "total_minutes": 0}
        )
        ranges = re.split(
            r"\s+and\s+|\s*;\s*",
            match.group("ranges"),
            flags=re.IGNORECASE,
        )
        for time_range in ranges:
            segment = _parse_past_hours_range(time_range, line_number)
            intervals["segments"].append(segment)
            intervals["total_minutes"] += segment["minutes"]

    if not shifts_by_date:
        raise ValueError("Enter at least one dated work interval.")

    parsed_shifts = []
    for shift in sorted(shifts_by_date.values(), key=lambda item: item["date"]):
        segments = sorted(shift["segments"], key=lambda item: item["start_minute"])
        for previous, current in pairwise(segments):
            if current["start_minute"] < previous["end_minute"]:
                raise ValueError(
                    f"Overlapping work intervals on "
                    f"{shift['date'].month}/{shift['date'].day}."
                )
        shift["segments"] = segments
        parsed_shifts.append(shift)
    return parsed_shifts


def _parse_past_hours_range(time_range: str, line_number: int) -> dict:
    match = PAST_HOURS_RANGE.fullmatch(time_range.strip())
    if match is None:
        raise ValueError(
            f"Invalid time range on line {line_number}: {time_range}. "
            "Use ranges like 9:00 am - 1:30 pm."
        )

    start_hour = int(match.group("start_hour"))
    end_hour = int(match.group("end_hour"))
    start_minute = int(match.group("start_minute"))
    end_minute = int(match.group("end_minute"))
    start_period = (match.group("start_period") or "").upper()
    end_period = (match.group("end_period") or "").upper()
    if (
        not 1 <= start_hour <= 12
        or not 1 <= end_hour <= 12
        or start_minute > 59
        or end_minute > 59
    ):
        raise ValueError(f"Invalid time on line {line_number}: {time_range}.")
    if not start_period and not end_period:
        raise ValueError(
            f"Specify AM or PM on at least one time in line {line_number}."
        )
    if not start_period:
        start_period = end_period
        if _minutes_since_midnight(start_hour, start_minute, start_period) >= (
            _minutes_since_midnight(end_hour, end_minute, end_period)
        ):
            start_period = "AM" if end_period == "PM" else "PM"
    if not end_period:
        end_period = start_period

    start_total = _minutes_since_midnight(start_hour, start_minute, start_period)
    end_total = _minutes_since_midnight(end_hour, end_minute, end_period)
    if end_total <= start_total:
        raise ValueError(
            f"End time must be later than start time on line {line_number}: "
            f"{time_range}."
        )

    return {
        "start": _format_past_hours_time(start_hour, start_minute, start_period),
        "end": _format_past_hours_time(end_hour, end_minute, end_period),
        "start_minute": start_total,
        "end_minute": end_total,
        "minutes": end_total - start_total,
    }


def _minutes_since_midnight(hour: int, minute: int, period: str) -> int:
    hour_24 = hour % 12 + (12 if period == "PM" else 0)
    return hour_24 * 60 + minute


def _format_past_hours_time(hour: int, minute: int, period: str) -> str:
    return f"{hour}:{minute:02d} {period}"


def minutes_as_hours(minutes: int) -> Decimal:
    return (Decimal(minutes) / Decimal(60)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _previous_month_label(month_label: str) -> str:
    month_date = datetime.strptime(month_label, "%B, %Y")
    previous_month = month_date.replace(day=1) - timedelta(days=1)
    return previous_month.strftime("%B, %Y")
