import json
from datetime import datetime
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import ScheduleImport, Shift, ShiftEntry


class KronosTextUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scheduler")
        self.client.force_login(self.user)

    def test_importing_raw_kronos_text_creates_shifts_and_segments(self):
        raw_text = (
            "October, 2026\n"
            "26 Monday\n"
            "10:00 AM - 5:00 PM [7.00]\n"
            "10:00 AM - 2:30 PM [4.50]\n"
            "2:30 PM - 3:30 PM [1.00] Break\n"
            "3:30 PM - 5:00 PM [1.50]\n"
            "27 Tuesday\n"
            "-\n"
            "Approved [38]\n"
        )

        response = self.client.post(
            reverse("schedule_upload"),
            {"raw_text": raw_text},
        )

        self.assertRedirects(response, reverse("schedule_list"))
        import_record = ScheduleImport.objects.get(uploaded_by=self.user)
        self.assertEqual(import_record.raw_text, raw_text)
        self.assertEqual(import_record.schedule_period, "October, 2026")

        shifts = list(
            Shift.objects.filter(schedule_import=import_record).order_by("date")
        )
        self.assertEqual(
            [shift.date.isoformat() for shift in shifts],
            ["2026-10-26", "2026-10-27"],
        )
        self.assertEqual(shifts[0].total_hours, 7)
        self.assertEqual(shifts[0].segments.count(), 3)
        self.assertEqual(
            list(shifts[0].segments.values_list("segment_type", flat=True)),
            ["work", "break", "work"],
        )
        self.assertEqual(shifts[1].total_hours, 0)
        self.assertFalse(shifts[1].segments.exists())

        visible_shift = ShiftEntry.objects.get(
            user=self.user, date="2026-10-26"
        )
        self.assertEqual(visible_shift.overall_time, "10:00 AM - 5:00 PM")
        self.assertEqual(visible_shift.gross_hours, 7)
        self.assertEqual(visible_shift.break_time, "2:30 PM - 3:30 PM")
        self.assertEqual(visible_shift.break_hours, 1)
        self.assertEqual(
            visible_shift.segments,
            [
                "10:00 AM - 2:30 PM [4.50]",
                "2:30 PM - 3:30 PM [1.00]",
                "3:30 PM - 5:00 PM [1.50]",
            ],
        )
        self.assertTrue(
            ShiftEntry.objects.get(user=self.user, date="2026-10-27").is_off
        )

    def test_pasting_schedule_updates_existing_entries_only_for_that_user(self):
        date = datetime.strptime("09 November, 2026", "%d %B, %Y").date()
        ShiftEntry.objects.create(
            user=self.user,
            date=date,
            overall_time="Old shift",
            gross_hours=2,
        )
        previous_import = ScheduleImport.objects.create(
            uploaded_by=self.user,
            raw_text="Previous schedule",
            schedule_period="November, 2026",
        )
        previous_shift = Shift.objects.create(
            schedule_import=previous_import,
            date=date,
            total_hours=2,
            is_active=True,
        )
        other_user = User.objects.create_user(username="another-scheduler")
        other_import = ScheduleImport.objects.create(
            uploaded_by=other_user,
            raw_text="Old schedule",
            schedule_period="November, 2026",
        )
        other_shift = Shift.objects.create(
            schedule_import=other_import,
            date=date,
            total_hours=2,
            is_active=True,
        )
        raw_text = (
            "November, 2026\n"
            "09 Monday\n"
            "-\n"
            "Approved [47]\n"
            "In Progress [1]\n"
            "3:00 PM - 9:00 PM [6.00]\n"
            "3:00 PM - 6:00 PM [3.00]\n"
            "6:00 PM - 6:30 PM [0.50] Break\n"
            "6:30 PM - 9:00 PM [2.50]\n"
        )

        response = self.client.post(
            reverse("schedule_upload"),
            {"raw_text": raw_text},
        )

        self.assertRedirects(response, reverse("schedule_list"))
        self.assertEqual(ShiftEntry.objects.filter(user=self.user).count(), 1)
        visible_shift = ShiftEntry.objects.get(user=self.user, date=date)
        self.assertEqual(visible_shift.overall_time, "3:00 PM - 9:00 PM")
        self.assertEqual(visible_shift.gross_hours, 6)
        self.assertEqual(visible_shift.break_time, "6:00 PM - 6:30 PM")
        self.assertEqual(visible_shift.break_hours, 0.5)
        previous_shift.refresh_from_db()
        self.assertFalse(previous_shift.is_active)
        other_shift.refresh_from_db()
        self.assertTrue(other_shift.is_active)

        response = self.client.get(reverse("schedule_list"))
        self.assertContains(response, "3:00 PM - 9:00 PM")

    def test_raw_text_before_first_month_header_uses_previous_month(self):
        raw_text = "31 Saturday\n-\nNovember, 2026\n01 Sunday\n-\n"

        response = self.client.post(reverse("schedule_upload"), {"raw_text": raw_text})

        self.assertRedirects(response, reverse("schedule_list"))
        dates = list(Shift.objects.order_by("date").values_list("date", flat=True))
        self.assertEqual(
            [shift_date.isoformat() for shift_date in dates],
            ["2026-10-31", "2026-11-01"],
        )
        self.assertEqual(
            ScheduleImport.objects.get(uploaded_by=self.user).schedule_period,
            "October, 2026 - November, 2026",
        )

    def test_invalid_raw_text_is_reported_without_creating_import(self):
        response = self.client.post(
            reverse("schedule_upload"),
            {"raw_text": "This is not a Kronos schedule"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No month and year header found")
        self.assertFalse(ScheduleImport.objects.exists())


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
        self.assertEqual(entry.date.isoformat(), "2026-10-26")
        self.assertEqual(entry.overall_time, "10:00 AM - 2:00 PM")
        self.assertFalse(entry.is_off)

    def test_saving_shift_with_iso_date(self):
        response = self.client.post(
            reverse("save_shifts_api"),
            data=json.dumps(
                {
                    "shifts": [
                        {
                            "date": "2026-11-02",
                            "overallTime": "10:00 AM - 2:00 PM",
                            "grossHours": 4,
                        }
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ShiftEntry.objects.filter(user=self.user, date="2026-11-02").exists()
        )


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
            schedule_date = datetime.strptime(
                f"{date_str.split()[0]} {month}", "%d %B, %Y"
            ).date()
            ShiftEntry.objects.create(
                user=self.user,
                date=schedule_date,
                overall_time=(
                    "10:00 AM - 2:00 PM"
                    if schedule_date.isoformat() == "2026-11-02"
                    else ""
                ),
                gross_hours=4 if schedule_date.isoformat() == "2026-11-02" else 0,
            )

        response = self.client.get(reverse("schedule_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["shifts"].values_list("date", flat=True)),
            [
                datetime(2026, 11, 2).date(),
                datetime(2026, 11, 1).date(),
                datetime(2026, 10, 31).date(),
                datetime(2026, 10, 30).date(),
            ],
        )
        self.assertContains(response, 'id="filter-start-date"')
        self.assertContains(response, 'data-date="2026-11-02"')
        self.assertContains(response, 'id="calendar-view"')
        self.assertContains(response, 'id="calendar-view-button"')
        self.assertContains(response, 'data-overall-time="10:00 AM - 2:00 PM"')
        self.assertContains(response, "function renderCalendar()")
        self.assertContains(response, "if (row.dataset.status === 'OFF') return;")
        self.assertNotContains(response, "Off / None ·")
        self.assertContains(response, "const endDate = dates[dates.length - 1]")
        self.assertContains(response, "for (let date = start; date <= end;")
        self.assertContains(response, "container.appendChild(grid)")
        self.assertContains(
            response, "No scheduled dates from the selected start date."
        )
        self.assertContains(
            response, "['Sat', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri']"
        )
        self.assertContains(response, "Monday, November 2, 2026")
        self.assertContains(
            response, 'id="date-column" class="py-3 ps-3" aria-sort="descending"'
        )
        self.assertContains(response, 'id="sort-date"')
        self.assertContains(response, "function toggleDateSort()")
        self.assertContains(response, "function updateExportLink()")
        self.assertContains(
            response, "exportUrl.searchParams.set('view', currentScheduleView)"
        )
        self.assertContains(response, "getAttribute('aria-sort')")
        self.assertContains(response, "earliest to latest")

    def test_schedule_pdf_contains_only_the_users_schedule_table(self):
        ShiftEntry.objects.create(
            user=self.user,
            date=datetime(2026, 11, 2).date(),
            overall_time="10:00 AM - 2:00 PM",
            gross_hours=4,
        )
        other_user = User.objects.create_user(username="other", password="test-pass")
        ShiftEntry.objects.create(
            user=other_user,
            date=datetime(2026, 11, 3).date(),
        )

        response = self.client.get(reverse("schedule_export_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].endswith('.pdf"'))
        self.assertTrue(response.content.startswith(b"%PDF"))

    @patch("scheduler.views.HTML")
    @patch("scheduler.views.render_to_string", return_value="<table></table>")
    def test_schedule_pdf_applies_date_status_month_and_sort_filters(
        self, render_template, pdf_renderer
    ):
        entries = [
            ("November, 2026", "01 Sunday", True),
            ("November, 2026", "02 Monday", False),
            ("November, 2026", "03 Tuesday", False),
            ("October, 2026", "31 Saturday", False),
        ]
        for month, date_str, is_off in entries:
            schedule_date = datetime.strptime(
                f"{date_str.split()[0]} {month}", "%d %B, %Y"
            ).date()
            ShiftEntry.objects.create(
                user=self.user,
                date=schedule_date,
                is_off=is_off,
            )
        pdf_renderer.return_value.write_pdf.return_value = b"%PDF test"

        filters = {
            "start_date": "2026-11-01",
            "month": "November, 2026",
            "status": "SCHEDULED",
        }
        for direction, expected_order in (
            ("ascending", ["02 Monday", "03 Tuesday"]),
            ("descending", ["03 Tuesday", "02 Monday"]),
        ):
            with self.subTest(direction=direction):
                response = self.client.get(
                    reverse("schedule_export_pdf"),
                    {**filters, "sort": direction},
                )

                self.assertEqual(response.status_code, 200)
                exported_shifts = render_template.call_args.args[1]["shifts"]
                self.assertEqual(
                    [shift.date.strftime("%d") for shift in exported_shifts],
                    [date.split()[0] for date in expected_order],
                )

        response = self.client.get(
            reverse("schedule_export_pdf"),
            {"month": "November, 2026"},
        )
        self.assertEqual(response.status_code, 200)
        exported_shifts = render_template.call_args.args[1]["shifts"]
        self.assertEqual(
            {shift.date.strftime("%B, %Y") for shift in exported_shifts},
            {"November, 2026"},
        )

    @patch("scheduler.views.HTML")
    @patch("scheduler.views.render_to_string", return_value="<table></table>")
    def test_calendar_pdf_uses_continuous_saturday_first_calendar(
        self, render_template, pdf_renderer
    ):
        for month, date_str in (
            ("November, 2026", "01 Sunday"),
            ("November, 2026", "02 Monday"),
            ("November, 2026", "07 Saturday"),
        ):
            schedule_date = datetime.strptime(
                f"{date_str.split()[0]} {month}", "%d %B, %Y"
            ).date()
            ShiftEntry.objects.create(
                user=self.user,
                date=schedule_date,
                overall_time="10:00 AM - 2:00 PM",
                gross_hours=4,
            )
        pdf_renderer.return_value.write_pdf.return_value = b"%PDF test"

        response = self.client.get(
            reverse("schedule_export_pdf"),
            {"view": "calendar", "start_date": "2026-11-02"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_template.call_args.args[0],
            "scheduler/schedule_export_calendar_pdf.html",
        )
        weeks = render_template.call_args.args[1]["calendar_weeks"]
        self.assertEqual(len(weeks), 2)
        self.assertEqual(
            [day["date"].isoformat() for day in weeks[0]],
            [
                "2026-10-31",
                "2026-11-01",
                "2026-11-02",
                "2026-11-03",
                "2026-11-04",
                "2026-11-05",
                "2026-11-06",
            ],
        )
        self.assertFalse(weeks[0][0]["in_range"])
        self.assertEqual(
            [shift.date.isoformat() for shift in weeks[0][2]["shifts"]],
            ["2026-11-02"],
        )
        self.assertTrue(weeks[0][2]["month_label"])
        self.assertEqual(weeks[1][0]["date"].isoformat(), "2026-11-07")

    @patch("scheduler.views.HTML")
    def test_calendar_pdf_template_leaves_off_shift_details_blank(self, pdf_renderer):
        ShiftEntry.objects.create(
            user=self.user,
            date=datetime(2026, 11, 6).date(),
            is_off=True,
            gross_hours=0,
        )
        pdf_renderer.return_value.write_pdf.return_value = b"%PDF test"

        response = self.client.get(
            reverse("schedule_export_pdf"),
            {"view": "calendar"},
        )

        self.assertEqual(response.status_code, 200)
        html = pdf_renderer.call_args.kwargs["string"]
        self.assertIn("6", html)
        self.assertNotIn("Off / None", html)
        self.assertNotIn("0.00 hrs", html)
