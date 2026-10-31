import re
from datetime import datetime, timedelta

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


def _previous_month_label(month_label: str) -> str:
    month_date = datetime.strptime(month_label, "%B, %Y")
    previous_month = month_date.replace(day=1) - timedelta(days=1)
    return previous_month.strftime("%B, %Y")
