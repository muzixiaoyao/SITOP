# Add M2M groups field to Server (step 1 of FK->M2M migration)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0003_servergroup_auto_patrol"),
    ]

    operations = [
        migrations.AddField(
            model_name="server",
            name="groups",
            field=models.ManyToManyField(
                blank=True,
                related_name="servers_new",
                to="servers.servergroup",
            ),
        ),
    ]
