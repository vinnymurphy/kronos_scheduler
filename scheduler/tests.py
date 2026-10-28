import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import ShiftEntry


class SaveShiftsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scheduler", password="test-pass")
        self.client.force_login(self.user)

    def test_saving_repeated_date_updates_existing_entry(self):
        shifts = [
            {
                "month": "October, 2026",
                "dateStr": "26 Monday",
                "dayNum": "26",
                "dayName": "Monday",
                "isOff": True,
                "overallTime": "",
                "grossHours": 0,
            },
            {
                "month": "October, 2026",
                "dateStr": "26 Monday",
                "dayNum": "26",
                "dayName": "Monday",
                "isOff": False,
                "overallTime": "10:00 AM - 2:00 PM",
                "grossHours": 4,
            },
        ]

        response = self.client.post(
            reverse("save_shifts_api"),
            data=json.dumps({"shifts": shifts}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["message"], "Successfully saved 1 shift records!"
        )
        self.assertEqual(ShiftEntry.objects.filter(user=self.user).count(), 1)
        entry = ShiftEntry.objects.get(user=self.user)
        self.assertEqual(entry.overall_time, "10:00 AM - 2:00 PM")
        self.assertFalse(entry.is_off)


class ScheduleListOrderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scheduler", password="test-pass")
        self.client.force_login(self.user)

    def test_schedule_list_orders_latest_date_first_across_months(self):
        entries = [
            ("October, 2026", "30 Friday"),
            ("November, 2026", "02 Monday"),
            ("October, 2026", "31 Saturday"),
            ("November, 2026", "01 Sunday"),
        ]
        for month, date_str in entries:
            day_num, day_name = date_str.split()
            ShiftEntry.objects.create(
                user=self.user,
                month=month,
                date_str=date_str,
                day_num=day_num,
                day_name=day_name,
            )

        response = self.client.get(reverse("schedule_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["shifts"].values_list("date_str", flat=True)),
            ["02 Monday", "01 Sunday", "31 Saturday", "30 Friday"],
        )
        self.assertContains(response, 'id="filter-start-date"')
        self.assertContains(response, 'data-date="2026-11-02"')
