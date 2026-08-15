# Add remaining missing fields to SSHCredential

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_sshcredential_jump_host_sshcredential_jump_port_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sshcredential",
            name="token",
            field=models.BinaryField(blank=True, help_text="临时Token（加密存储）", null=True),
        ),
        migrations.AddField(
            model_name="sshcredential",
            name="use_ssh_agent",
            field=models.BooleanField(default=False, help_text="使用SSH Agent转发"),
        ),
        migrations.AddField(
            model_name="sshcredential",
            name="connect_timeout",
            field=models.PositiveIntegerField(default=15, help_text="连接超时（秒）"),
        ),
        migrations.AddField(
            model_name="sshcredential",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="sshcredential",
            name="auth_type",
            field=models.CharField(
                choices=[
                    ("password", "密码"),
                    ("key", "SSH密钥"),
                    ("key_with_passphrase", "SSH密钥+密码"),
                    ("token", "临时Token"),
                ],
                default="password",
                max_length=20,
            ),
        ),
    ]
