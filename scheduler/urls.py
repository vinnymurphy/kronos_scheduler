from django.urls import path

from .views import (
    kronos_parser_view,
    save_shifts_api,
    schedule_list_view,
    schedule_upload_view,
)

urlpatterns = [
    path("", schedule_list_view, name="schedule_list"),
    path("upload/", schedule_upload_view, name="schedule_upload"),
    path("parser/", kronos_parser_view, name="kronos_parser"),
    path("api/save-shifts/", save_shifts_api, name="save_shifts_api"),
]
