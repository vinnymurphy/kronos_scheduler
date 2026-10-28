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
        return f"Import by {self.uploaded_by} on {self.created_at:%Y-%m-%d %H:%M}"


class Shift(models.Model):
    """Normalized shift data parsed from a Kronos schedule import."""

    schedule_import = models.ForeignKey(
        ScheduleImport,
        on_delete=models.CASCADE,
        related_name="shifts",
    )
    date = models.DateField()
    day_of_week = models.CharField(max_length=20, blank=True, default="")
    total_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="False if a newer schedule upload has overridden this date's schedule.",
    )

    class Meta:
        ordering = ("date",)
        constraints = (
            models.UniqueConstraint(
                fields=("schedule_import", "date"),
                name="unique_schedule_import_date",
            ),
        )

    def clean(self):
        super().clean()
        if not self.day_of_week and self.date:
            self.day_of_week = self.date.strftime("%A")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} ({self.total_hours} hrs)"


class ShiftSegment(models.Model):
    """A single work or break block inside a shift."""

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
        if self.hours < Decimal("0.00"):
            raise ValidationError({"hours": "Segment hours cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.segment_type.capitalize()}: {self.start_time} - {self.end_time}"


class ShiftEntry(models.Model):
    """
    Employee daily schedule entry.

    Use `date` as the canonical field. The month/day_num/day_name/date_str values
    are provided as compatibility properties so existing code keeps working while
    we transition to a cleaner model.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="shift_entries",
    )

    # Canonical field
    date = models.DateField()

    # Structured data
    is_off = models.BooleanField(default=False)
    gross_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    break_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    overall_time = models.CharField(max_length=50, blank=True, null=True)
    break_time = models.CharField(max_length=50, blank=True, null=True)

    segments = models.JSONField(default=list, blank=True)

    approved = models.IntegerField(blank=True, null=True)
    in_progress = models.IntegerField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("user", "date"),
                name="unique_user_schedule_day",
            ),
            models.CheckConstraint(
                condition=models.Q(gross_hours__gte=Decimal("0.00")),
                name="shiftentry_gross_hours_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(break_hours__gte=Decimal("0.00")),
                name="shiftentry_break_hours_non_negative",
            ),
        )
        ordering = ("date",)

    def clean(self):
        super().clean()
        if self.gross_hours < Decimal("0.00"):
            raise ValidationError({"gross_hours": "Gross hours cannot be negative."})
        if self.break_hours < Decimal("0.00"):
            raise ValidationError({"break_hours": "Break hours cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def month(self):
        return self.date.strftime("%B, %Y") if self.date else ""

    @property
    def day_num(self):
        return str(self.date.day) if self.date else ""

    @property
    def day_name(self):
        return self.date.strftime("%A") if self.date else ""

    @property
    def date_str(self):
        return self.date.strftime("%A, %B %d, %Y") if self.date else ""

    @property
    def schedule_date(self):
        return self.date

    def __str__(self):
        status = "Off" if self.is_off else f"{self.gross_hours} hrs"
        return f"{self.date} ({status})"
