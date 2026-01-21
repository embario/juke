from django.contrib import admin

from .models import PowerHourSession, SessionPlayer, SessionTrack


class SessionPlayerInline(admin.TabularInline):
    model = SessionPlayer
    extra = 0
    readonly_fields = ('id', 'joined_at')


class SessionTrackInline(admin.TabularInline):
    model = SessionTrack
    extra = 0
    readonly_fields = ('id', 'added_at')


@admin.register(PowerHourSession)
class PowerHourSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'admin', 'invite_code', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('title', 'invite_code')
    readonly_fields = ('id', 'invite_code', 'created_at', 'started_at', 'ended_at')
    inlines = [SessionPlayerInline, SessionTrackInline]


@admin.register(SessionPlayer)
class SessionPlayerAdmin(admin.ModelAdmin):
    list_display = ('user', 'session', 'is_admin', 'joined_at')
    list_filter = ('is_admin',)


@admin.register(SessionTrack)
class SessionTrackAdmin(admin.ModelAdmin):
    list_display = ('track', 'session', 'order', 'added_by', 'added_at')
    list_filter = ('session',)
