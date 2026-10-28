from datetime import datetime

from django.db import migrations, models
from django.db.models import Count


def populate_shift_entry_dates(apps, schema_editor):
    ShiftEntry = apps.get_model("scheduler", "ShiftEntry")
    database = schema_editor.connection.alias

    for entry in ShiftEntry.objects.using(database).all().iterator():
        try:
            entry_date = datetime.strptime(
                f"{entry.day_num} {entry.month}", "%d %B, %Y"
            ).date()
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                f"Cannot convert ShiftEntry {entry.pk} "
                f"from {entry.day_num!r} {entry.month!r} to a date."
            ) from error
        entry.date = entry_date
        entry.save(using=database, update_fields=("date",))

    duplicates = (
        ShiftEntry.objects.using(database)
        .filter(user_id__isnull=False)
        .values("user_id", "date")
        .annotate(entry_count=Count("id"))
        .filter(entry_count__gt=1)
    )
    duplicate = duplicates.order_by("user_id", "date").first()
    if duplicate:
        raise RuntimeError(
            "Multiple ShiftEntry records exist for user "
            f"{duplicate['user_id']} on {duplicate['date']}; resolve duplicates "
            "before migrating to one entry per date."
        )


class Migration(migrations.Migration):
    dependencies = (("scheduler", "0004_alter_scheduleimport_options_and_more"),)

    operations = (
        migrations.AddField(
            model_name="shiftentry",
            name="date",
            field=models.DateField(null=True),
        ),
        migrations.RunPython(
            populate_shift_entry_dates,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="shiftentry",
            name="unique_user_schedule_day",
        ),
        migrations.RemoveField(
            model_name="shiftentry",
            name="date_str",
        ),
        migrations.RemoveField(
            model_name="shiftentry",
            name="day_num",
        ),
        migrations.RemoveField(
            model_name="shiftentry",
            name="day_name",
        ),
        migrations.RemoveField(
            model_name="shiftentry",
            name="month",
        ),
        migrations.AlterField(
            model_name="shiftentry",
            name="date",
            field=models.DateField(),
        ),
        migrations.AlterModelOptions(
            name="shiftentry",
            options={"ordering": ("date",)},
        ),
        migrations.AddConstraint(
            model_name="shiftentry",
            constraint=models.UniqueConstraint(
                fields=("user", "date"),
                name="unique_user_schedule_date",
            ),
        ),
    )
