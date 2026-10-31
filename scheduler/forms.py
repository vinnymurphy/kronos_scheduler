from django.forms import CharField, FileField, Form, Textarea


class ScheduleUploadForm(Form):
    json_file = FileField(
        required=False,
        help_text="Upload a structured Kronos JSON file if available.",
    )
    raw_text = CharField(
        required=False,
        strip=False,
        widget=Textarea(
            attrs={
                "rows": 10,
                "placeholder": ("Paste your raw Kronos text schedule here..."),
            }
        ),
        help_text="Paste structured Kronos JSON or raw Kronos schedule text.",
    )
