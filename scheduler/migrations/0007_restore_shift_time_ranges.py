from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = (
        ("scheduler", "0006_remove_shiftentry_unique_user_schedule_date_and_more"),
    )

    operations = (
        migrations.AlterField(
            model_name="shiftentry",
            name="overall_time",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name="shiftentry",
            name="break_time",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name="shiftentry",
            name="approved",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="shiftentry",
            name="in_progress",
            field=models.IntegerField(blank=True, null=True),
        ),
    )
