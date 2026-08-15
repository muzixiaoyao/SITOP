# Data migration: copy group FK to groups M2M (step 2 of FK->M2M migration)

from django.db import migrations


def migrate_group_to_groups(apps, schema_editor):
    Server = apps.get_model("servers", "Server")
    ServerGroup = apps.get_model("servers", "ServerGroup")

    for server in Server.objects.all():
        if server.group_id:
            server.groups.add(server.group_id)
        else:
            # Fallback: assign to default group
            first_group = ServerGroup.objects.first()
            if first_group:
                tenant = first_group.tenant
                default_group, _ = ServerGroup.objects.get_or_create(
                    tenant=tenant,
                    name="未分组",
                    defaults={"description": "默认分组"},
                )
                server.groups.add(default_group)


def reverse_migrate(apps, schema_editor):
    Server = apps.get_model("servers", "Server")
    for server in Server.objects.all():
        first_group = server.groups.first()
        if first_group:
            server.group = first_group
            server.save(update_fields=["group"])


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0004_server_groups_m2m"),
    ]

    operations = [
        migrations.RunPython(migrate_group_to_groups, reverse_migrate),
    ]
