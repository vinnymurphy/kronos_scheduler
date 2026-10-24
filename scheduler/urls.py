from django.urls import path

from .views import schedule_list_view, schedule_upload_view, kronos_parser_view

urlpatterns = [
    path("", schedule_list_view, name="schedule_list"),
    path("upload/", schedule_upload_view, name="schedule_upload"),
    path("kronos-parser/", kronos_parser_view, name="kronos_parser"),
]
