from django.contrib.auth.models import User
from django.db import models


class ScheduleImport(models.Model):
    """Tracks every raw upload or paste from Kronos to maintain schedule history."""

    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    raw_text = models.TextField(help_text="Raw Kronos text or JSON pasted.")
    schedule_period = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Import by {self.uploaded_by} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class Shift(models.Model):
    schedule_import = models.ForeignKey(
        ScheduleImport, on_delete=models.CASCADE, related_name="shifts"
    )
    date = models.DateField()
    day_of_week = models.CharField(max_length=20)
    total_hours = models.DecimalField(max_digits=4, decimal_places=2)
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "False if a newer schedule upload has overridden this date's schedule."
        ),
    )

    class Meta:
        # Use tuple to satisfy Ruff RUF012 (immutable)
        ordering = ("date",)

    def __str__(self):
        return f"{self.date} ({self.total_hours} hrs)"


class ShiftSegment(models.Model):
    # Use tuples for choices to satisfy Ruff RUF012
    SEGMENT_TYPES = (
        ("work", "Work"),
        ("break", "Break"),
    )
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="segments")
    segment_type = models.CharField(max_length=10, choices=SEGMENT_TYPES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    hours = models.DecimalField(max_digits=4, decimal_places=2)

    def __str__(self):
        return f"{self.segment_type.capitalize()}: {self.start_time} - {self.end_time}"
