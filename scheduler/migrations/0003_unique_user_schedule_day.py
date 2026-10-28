from django.db import migrations, models
from django.db.models import Count


def remove_duplicate_schedule_days(apps, schema_editor):
    ShiftEntry = apps.get_model("scheduler", "ShiftEntry")
    database = schema_editor.connection.alias
    duplicates = (
        ShiftEntry.objects.using(database)
        .filter(user_id__isnull=False)
        .values("user_id", "month", "day_num")
        .annotate(entry_count=Count("id"))
        .filter(entry_count__gt=1)
    )

    for duplicate in duplicates.iterator():
        entries = (
            ShiftEntry.objects.using(database)
            .filter(
                user_id=duplicate["user_id"],
                month=duplicate["month"],
                day_num=duplicate["day_num"],
            )
            .order_by("-updated_at", "-id")
        )
        entries.exclude(pk=entries.first().pk).delete()


class Migration(migrations.Migration):
    dependencies = (("scheduler", "0002_shiftentry"),)

    operations = (
        migrations.RunPython(
            remove_duplicate_schedule_days,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="shiftentry",
            constraint=models.UniqueConstraint(
                fields=("user", "month", "day_num"),
                name="unique_user_schedule_day",
            ),
        ),
    )
