import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ScheduleUploadForm
from .models import Shift
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