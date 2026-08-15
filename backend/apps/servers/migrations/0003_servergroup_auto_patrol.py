from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0002_server_extra_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="servergroup",
            name="auto_patrol",
            field=models.BooleanField(default=True),
        ),
    ]
