import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .forms import ScheduleUploadForm
from .models import Shift, ShiftEntry
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


@login_required
def schedule_list_view(request):
    # Retrieve only the currently active shifts for you
    active_shifts = Shift.objects.filter(is_active=True).prefetch_related("segments")
    return render(request, "scheduler/schedule_list.html", {"shifts": active_shifts})


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

            saved_count = 0
            for s in shifts_data:
                ShiftEntry.objects.update_or_create(
                    user=request.user,
                    month=s.get("month"),
                    date_str=s.get("dateStr"),
                    defaults={
                        "day_num": s.get("dayNum"),
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
                saved_count += 1

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
