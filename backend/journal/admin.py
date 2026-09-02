from django.contrib import admin

from journal.models import JournalAccountCapability


@admin.register(JournalAccountCapability)
class JournalAccountCapabilityAdmin(admin.ModelAdmin):
    list_display = ('user', 'cloud_ai_enabled', 'modified_at')
    list_filter = ('cloud_ai_enabled',)
    search_fields = ('user__username', 'user__email')
