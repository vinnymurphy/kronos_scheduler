import json
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Case, IntegerField, Value, When
from django.db.models.functions import Cast
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from weasyprint import HTML

from .forms import ScheduleUploadForm
from .models import ShiftEntry
from .services import import_schedule_json


@login_required
def schedule_upload_view(request):
    if request.method == "POST":
        form = ScheduleUploadForm(request.POST, request.FILES)
        if form.is_valid():
            json_data = None

            # Check if a JSON file was uploaded
            json_file = request.FILES.get("json_file")
            if json_file:
                try:
                    json_data = json.load(json_file)
                except json.JSONDecodeError as e:
                    form.add_error("json_file", f"Invalid JSON file: {e}")

            # Otherwise, check if raw text was pasted
            elif form.cleaned_data.get("raw_text"):
                raw_input = form.cleaned_data["raw_text"]
                try:
                    json_data = json.loads(raw_input)
                except json.JSONDecodeError as e:
                    form.add_error(
                        "raw_text",
                        f"Invalid JSON format in text paste. Please provide valid JSON: {e}",
                    )

            if json_data and not form.errors:
                import_schedule_json(request.user, json_data)
                return redirect("schedule_list")
    else:
        form = ScheduleUploadForm()

    return render(request, "scheduler/upload.html", {"form": form})


def kronos_parser_view(request):
    return render(request, "scheduler/kronos_parser.html")


@login_required
@csrf_exempt  # (Optional: remove if passing Django's CSRF token from JS header)
def save_shifts_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            shifts_data = data.get("shifts", [])

            # Optional: Clear existing entries for a fresh sync or update iteratively
            # ShiftEntry.objects.filter(user=request.user).delete()

            with transaction.atomic():
                for s in shifts_data:
                    ShiftEntry.objects.update_or_create(
                        user=request.user,
                        month=s.get("month"),
                        day_num=s.get("dayNum"),
                        defaults={
                            "date_str": s.get("dateStr"),
                            "day_name": s.get("dayName"),
                            "is_off": s.get("isOff", False),
                            "overall_time": s.get("overallTime", ""),
                            "gross_hours": s.get("grossHours", 0),
                            "break_time": s.get("breakTime", ""),
                            "break_hours": s.get("breakHours", 0),
                            "segments": s.get("segments", []),
                            "approved": s.get("approved"),
                            "in_progress": s.get("inProgress"),
                        },
                    )
                saved_count = len(
                    {(s.get("month"), s.get("dayNum")) for s in shifts_data}
                )

            return JsonResponse(
                {
                    "status": "success",
                    "message": f"Successfully saved {saved_count} shift records!",
                }
            )
        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ValidationError,
            DatabaseError,
        ) as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    return JsonResponse(
        {"status": "error", "message": "Invalid request method."}, status=405
    )


@login_required
def schedule_list_view(request):
    user_shifts = ShiftEntry.objects.filter(user=request.user)
    shifts = get_schedule_shifts(request.user)
    # Extract distinct months for the filter dropdown
    unique_months = user_shifts.values_list("month", flat=True).distinct()

    return render(
        request,
        "scheduler/schedule_list.html",
        {"shifts": shifts, "unique_months": unique_months},
    )


@login_required
def schedule_export_pdf_view(request):
    start_date_value = request.GET.get("start_date", "")
    start_date = parse_date(start_date_value) if start_date_value else None
    if start_date_value and start_date is None:
        return HttpResponseBadRequest("Invalid start date. Use YYYY-MM-DD.")

    month = request.GET.get("month", "ALL")
    status = request.GET.get("status", "ALL")
    sort_direction = request.GET.get("sort", "descending")
    view = request.GET.get("view", "table")
    if status not in {"ALL", "SCHEDULED", "OFF"}:
        return HttpResponseBadRequest("Invalid schedule status.")
    if sort_direction not in {"ascending", "descending"}:
        return HttpResponseBadRequest("Invalid sort direction.")
    if view not in {"table", "calendar"}:
        return HttpResponseBadRequest("Invalid schedule view.")

    all_shifts = list(get_schedule_shifts(request.user))
    shifts = all_shifts.copy()
    if start_date:
        shifts = [shift for shift in shifts if shift.schedule_date >= start_date]
    if month != "ALL":
        shifts = [shift for shift in shifts if shift.month == month]
    if status == "SCHEDULED":
        shifts = [shift for shift in shifts if not shift.is_off]
    elif status == "OFF":
        shifts = [shift for shift in shifts if shift.is_off]
    shifts.sort(
        key=lambda shift: shift.schedule_date,
        reverse=sort_direction == "descending",
    )

    if view == "calendar":
        range_start = start_date or min(
            (shift.schedule_date for shift in all_shifts), default=None
        )
        range_end = max((shift.schedule_date for shift in all_shifts), default=None)
        calendar_weeks = build_calendar_weeks(shifts, range_start, range_end)
        template_name = "scheduler/schedule_export_calendar_pdf.html"
        context = {"calendar_weeks": calendar_weeks}
    else:
        template_name = "scheduler/schedule_export_pdf.html"
        context = {"shifts": shifts}

    html = render_to_string(
        template_name,
        context,
    )
    pdf = HTML(
        string=html,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    pdf_file = f"schedule-{datetime.now().isoformat()}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{pdf_file}"'
    return response


def build_calendar_weeks(shifts, range_start, range_end):
    if range_start is None or range_end is None or range_start > range_end:
        return []

    shifts_by_date = {}
    for shift in shifts:
        shifts_by_date.setdefault(shift.schedule_date, []).append(shift)

    calendar_start = range_start - timedelta(days=(range_start.weekday() + 2) % 7)
    calendar_end = range_end + timedelta(days=(4 - range_end.weekday()) % 7)
    weeks = []
    current_day = calendar_start
    while current_day <= calendar_end:
        week = []
        for _ in range(7):
            week.append(
                {
                    "date": current_day,
                    "in_range": range_start <= current_day <= range_end,
                    "month_label": (current_day == range_start or current_day.day == 1),
                    "shifts": shifts_by_date.get(current_day, []),
                }
            )
            current_day += timedelta(days=1)
        weeks.append(week)
    return weeks


def get_schedule_shifts(user):
    user_shifts = ShiftEntry.objects.filter(user=user)
    months = list(user_shifts.values_list("month", flat=True).distinct())
    months.sort(key=lambda month: datetime.strptime(month, "%B, %Y"))
    month_order = Case(
        *[When(month=month, then=Value(index)) for index, month in enumerate(months)],
        default=Value(-1),
        output_field=IntegerField(),
    )
    return user_shifts.annotate(month_order=month_order).order_by(
        "-month_order", Cast("day_num", IntegerField()).desc()
    )
