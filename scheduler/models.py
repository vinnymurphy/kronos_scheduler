from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ScheduleImport(models.Model):
    """Tracks every raw upload or paste from Kronos to maintain schedule history."""

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="schedule_imports",
    )
    raw_text = models.TextField(help_text="Raw Kronos text or JSON pasted.")
    schedule_period = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return (
            f"Import by {self.uploaded_by} "
            f"on {self.created_at.strftime('%Y-%m-%d %H:%M')}"
        )


class Shift(models.Model):
    schedule_import = models.ForeignKey(
        ScheduleImport,
        on_delete=models.CASCADE,
        related_name="shifts",
    )
    date = models.DateField()
    day_of_week = models.CharField(max_length=20)
    total_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "False if a newer schedule upload has overridden this date's schedule."
        ),
    )

    class Meta:
        ordering = ("date",)
        constraints = (
            models.UniqueConstraint(
                fields=("schedule_import", "date"),
                name="unique_schedule_import_date",
            ),
        )

    def __str__(self):
        return f"{self.date} ({self.total_hours} hrs)"


class ShiftSegment(models.Model):
    SEGMENT_TYPES = (
        ("work", "Work"),
        ("break", "Break"),
    )

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="segments")
    segment_type = models.CharField(max_length=10, choices=SEGMENT_TYPES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=models.Q(start_time__lt=models.F("end_time")),
                name="shift_segment_start_before_end",
            ),
        )

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("End time must be later than start time.")

    def __str__(self):
        return f"{self.segment_type.capitalize()}: {self.start_time} - {self.end_time}"


class ShiftEntry(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="shift_entries",
    )
    month = models.CharField(max_length=50)
    date_str = models.CharField(max_length=50, blank=True, default="")
    day_num = models.CharField(max_length=10)
    day_name = models.CharField(max_length=20)
    is_off = models.BooleanField(default=False)
    overall_time = models.CharField(max_length=50, blank=True, null=True)
    gross_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    break_time = models.CharField(max_length=50, blank=True, null=True)
    break_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    segments = models.JSONField(default=list, blank=True)
    approved = models.IntegerField(blank=True, null=True)
    in_progress = models.IntegerField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("user", "month", "day_num"),
                name="unique_user_schedule_day",
            ),
        )
        ordering = ("month", "day_num")

    @property
    def schedule_date(self):
        try:
            return datetime.strptime(f"{self.day_num} {self.month}", "%d %B, %Y").date()
        except (TypeError, ValueError):
            return None

    def __str__(self):
        status = "Off" if self.is_off else f"{self.gross_hours} hrs"
        return f"{self.month} - {self.date_str} ({status})"
