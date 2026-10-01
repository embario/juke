from django.contrib import admin

from radio.models import Exclusion, ListeningEvent, Station, TrackReaction


class ExclusionInline(admin.TabularInline):
    model = Exclusion
    extra = 0
    fields = ('scope', 'kind', 'value', 'label')


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'kind', 'frequency', 'learning', 'updated_at')
    list_filter = ('kind', 'learning')
    search_fields = ('name', 'user__username')
    raw_id_fields = ('user',)
    inlines = [ExclusionInline]


@admin.register(Exclusion)
class ExclusionAdmin(admin.ModelAdmin):
    list_display = ('user', 'scope', 'kind', 'value', 'label', 'station', 'created_at')
    list_filter = ('scope', 'kind')
    search_fields = ('value', 'label', 'user__username')
    raw_id_fields = ('user', 'station')


@admin.register(TrackReaction)
class TrackReactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'spotify_track_id', 'reactions', 'station', 'updated_at')
    search_fields = ('spotify_track_id', 'user__username')
    raw_id_fields = ('user', 'station')


@admin.register(ListeningEvent)
class ListeningEventAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'spotify_track_id', 'station', 'position_ms', 'source', 'created_at')
    list_filter = ('event', 'source')
    search_fields = ('spotify_track_id', 'user__username')
    raw_id_fields = ('user', 'station')
    date_hierarchy = 'created_at'
