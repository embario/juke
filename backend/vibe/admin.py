from django.contrib import admin

from vibe.models import VibeAccountCapability


@admin.register(VibeAccountCapability)
class VibeAccountCapabilityAdmin(admin.ModelAdmin):
    list_display = ('user', 'cloud_ai_enabled', 'modified_at')
    list_filter = ('cloud_ai_enabled',)
    search_fields = ('user__username', 'user__email')
