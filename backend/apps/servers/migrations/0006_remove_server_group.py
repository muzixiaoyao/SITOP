# Remove old group FK and finalize M2M related_name (step 3 of FK->M2M migration)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0005_migrate_group_to_groups"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="server",
            name="group",
        ),
        migrations.AlterField(
            model_name="server",
            name="groups",
            field=models.ManyToManyField(
                blank=True,
                related_name="servers",
                to="servers.servergroup",
            ),
        ),
    ]
