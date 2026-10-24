from django.urls import path

from .views import schedule_list_view, schedule_upload_view

urlpatterns = [
    path("", schedule_list_view, name="schedule_list"),
    path("upload/", schedule_upload_view, name="schedule_upload"),
]
