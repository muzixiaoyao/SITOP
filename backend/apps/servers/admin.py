from django.contrib import admin
from .models import ServerGroup, Server


@admin.register(ServerGroup)
class ServerGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "server_count", "created_at")
    list_filter = ("tenant",)
    filter_horizontal = ()

    def server_count(self, obj):
        return obj.servers.count()


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("hostname", "ip", "ssh_port", "group_names", "connectivity_status")
    list_filter = ("connectivity_status", "groups")
    filter_horizontal = ("groups",)

    @admin.display(description="分组")
    def group_names(self, obj):
        return ", ".join(obj.groups.values_list("name", flat=True))
