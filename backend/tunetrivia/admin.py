from django.contrib import admin

from .models import (
    TuneTriviaSession,
    TuneTriviaPlayer,
    TuneTriviaRound,
    TuneTriviaGuess,
    TuneTriviaLeaderboardEntry,
)


class TuneTriviaPlayerInline(admin.TabularInline):
    model = TuneTriviaPlayer
    extra = 0
    readonly_fields = ('id', 'joined_at', 'total_score')


class TuneTriviaRoundInline(admin.TabularInline):
    model = TuneTriviaRound
    extra = 0
    readonly_fields = ('id', 'round_number', 'status', 'track_name', 'artist_name')
    fields = ('round_number', 'status', 'track_name', 'artist_name', 'preview_url')


@admin.register(TuneTriviaSession)
class TuneTriviaSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'host', 'mode', 'status', 'max_songs', 'created_at')
    list_filter = ('status', 'mode', 'created_at')
    search_fields = ('name', 'code', 'host__username')
    readonly_fields = ('id', 'code', 'created_at', 'started_at', 'finished_at')
    inlines = [TuneTriviaPlayerInline, TuneTriviaRoundInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'host', 'mode', 'status')
        }),
        ('Configuration', {
            'fields': ('max_songs', 'seconds_per_song', 'enable_trivia')
        }),
        ('Auto-Select Filters', {
            'fields': ('auto_select_decade', 'auto_select_genre', 'auto_select_artist'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'finished_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TuneTriviaPlayer)
class TuneTriviaPlayerAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'session', 'user', 'is_host', 'total_score', 'joined_at')
    list_filter = ('is_host', 'joined_at')
    search_fields = ('display_name', 'user__username', 'session__name')
    readonly_fields = ('id', 'joined_at')


class TuneTriviaGuessInline(admin.TabularInline):
    model = TuneTriviaGuess
    extra = 0
    readonly_fields = (
        'player',
        'song_guess',
        'artist_guess',
        'trivia_guess',
        'song_correct',
        'artist_correct',
        'trivia_correct',
        'points_earned',
    )


@admin.register(TuneTriviaRound)
class TuneTriviaRoundAdmin(admin.ModelAdmin):
    list_display = ('session', 'round_number', 'track_name', 'artist_name', 'status')
    list_filter = ('status',)
    search_fields = ('track_name', 'artist_name', 'session__name')
    readonly_fields = ('id', 'started_at', 'revealed_at')
    inlines = [TuneTriviaGuessInline]


@admin.register(TuneTriviaGuess)
class TuneTriviaGuessAdmin(admin.ModelAdmin):
    list_display = (
        'player',
        'round',
        'song_guess',
        'artist_guess',
        'trivia_guess',
        'song_correct',
        'artist_correct',
        'trivia_correct',
        'points_earned',
    )
    list_filter = ('song_correct', 'artist_correct', 'trivia_correct')
    search_fields = ('player__display_name', 'song_guess', 'artist_guess')
    readonly_fields = ('id', 'submitted_at')


@admin.register(TuneTriviaLeaderboardEntry)
class TuneTriviaLeaderboardEntryAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'total_score', 'total_games', 'total_correct_trivia', 'last_played_at')
    search_fields = ('display_name', 'user__username')
    readonly_fields = ('id', 'last_played_at')
