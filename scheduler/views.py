import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Case, IntegerField, Value, When
from django.db.models.functions import Cast
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

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
    months = list(user_shifts.values_list("month", flat=True).distinct())
    months.sort(key=lambda month: datetime.strptime(month, "%B, %Y"))
    month_order = Case(
        *[When(month=month, then=Value(index)) for index, month in enumerate(months)],
        default=Value(-1),
        output_field=IntegerField(),
    )
    shifts = user_shifts.annotate(month_order=month_order).order_by(
        "-month_order", Cast("day_num", IntegerField()).desc()
    )
    # Extract distinct months for the filter dropdown
    unique_months = user_shifts.values_list("month", flat=True).distinct()

    return render(
        request,
        "scheduler/schedule_list.html",
        {"shifts": shifts, "unique_months": unique_months},
    )
