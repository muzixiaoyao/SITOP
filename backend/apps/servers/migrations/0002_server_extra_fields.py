# Add missing fields to Server model that were not in 0001_initial

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="server",
            name="protocol",
            field=models.CharField(
                choices=[("ssh", "SSH"), ("rdp", "RDP"), ("telnet", "Telnet"), ("vnc", "VNC")],
                default="ssh", max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="server",
            name="platform",
            field=models.CharField(
                choices=[
                    ("linux", "Linux"), ("windows", "Windows"), ("unix", "Unix"),
                    ("network", "网络设备"), ("other", "其他"),
                ],
                default="linux", max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="server",
            name="connect_timeout",
            field=models.PositiveIntegerField(default=15, help_text="连接超时（秒）"),
        ),
        migrations.AddField(
            model_name="server",
            name="exec_timeout",
            field=models.PositiveIntegerField(default=600, help_text="执行超时（秒）"),
        ),
        migrations.AddField(
            model_name="server",
            name="ssh_options",
            field=models.JSONField(blank=True, default=dict, help_text="SSH选项: StrictHostKeyChecking, etc."),
        ),
        migrations.AddField(
            model_name="server",
            name="tags",
            field=models.JSONField(blank=True, default=list, help_text="自定义标签"),
        ),
        migrations.AddField(
            model_name="server",
            name="custom_fields",
            field=models.JSONField(blank=True, default=dict, help_text="自定义字段"),
        ),
        migrations.AddField(
            model_name="server",
            name="comment",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="server",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
