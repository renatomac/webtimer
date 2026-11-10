from django.contrib import admin, messages

from .models import Preset, SpotifyAccount, Studio, StudioMembership, Timer


class MembershipInline(admin.TabularInline):
    model = StudioMembership
    extra = 1
    autocomplete_fields = ["user"]


@admin.action(description="Revoke and regenerate display link")
def regenerate_links(modeladmin, request, queryset):
    for studio in queryset:
        studio.regenerate_display_token()
    messages.success(request, "Display links regenerated; old links no longer work.")


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "timezone"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MembershipInline]
    actions = [regenerate_links]


@admin.register(Preset)
class PresetAdmin(admin.ModelAdmin):
    list_display = ["name", "studio", "rounds", "round_seconds", "rest_seconds", "direction"]
    list_filter = ["studio"]


@admin.register(Timer)
class TimerAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "rounds", "duration", "interval", "direction", "status"]
    list_filter = ["status", "direction"]
    search_fields = ["name", "user__username"]


@admin.register(SpotifyAccount)
class SpotifyAccountAdmin(admin.ModelAdmin):
    list_display = ["user", "display_name", "spotify_user_id", "expires_at", "updated_at"]
    readonly_fields = ["access_token", "refresh_token", "expires_at", "created_at", "updated_at"]
    search_fields = ["user__username", "display_name", "spotify_user_id"]
