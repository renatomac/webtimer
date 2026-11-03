from django.contrib import admin, messages

from .models import Preset, Studio, StudioMembership


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
