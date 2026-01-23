from rest_framework import serializers

from .models import (
    TuneTriviaSession,
    TuneTriviaPlayer,
    TuneTriviaRound,
    TuneTriviaGuess,
    TuneTriviaLeaderboardEntry,
)


# ============================================================================
# Player Serializers
# ============================================================================

class TuneTriviaPlayerSerializer(serializers.ModelSerializer):
    """Serializer for player data."""

    class Meta:
        model = TuneTriviaPlayer
        fields = [
            'id', 'display_name', 'is_host', 'total_score', 'joined_at'
        ]
        read_only_fields = ['id', 'joined_at']


class AddPlayerSerializer(serializers.Serializer):
    """Input serializer for adding a manual player (Host Mode)."""
    display_name = serializers.CharField(max_length=100)


# ============================================================================
# Round Serializers
# ============================================================================

class TuneTriviaRoundSerializer(serializers.ModelSerializer):
    """Serializer for round data."""

    class Meta:
        model = TuneTriviaRound
        fields = [
            'id', 'round_number', 'status',
            'track_name', 'artist_name', 'album_name',
            'album_art_url', 'preview_url', 'trivia',
            'started_at', 'revealed_at'
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        """Hide track info if round is still playing (not revealed)."""
        data = super().to_representation(instance)
        if instance.status == TuneTriviaRound.Status.PLAYING:
            # Hide answers during gameplay
            data['track_name'] = '???'
            data['artist_name'] = '???'
            data['album_name'] = ''
            data['album_art_url'] = ''
            data['trivia'] = None
        return data


class TuneTriviaRoundRevealedSerializer(serializers.ModelSerializer):
    """Serializer for round data after reveal (shows all info)."""

    class Meta:
        model = TuneTriviaRound
        fields = [
            'id', 'round_number', 'status',
            'track_name', 'artist_name', 'album_name',
            'album_art_url', 'preview_url', 'trivia',
            'started_at', 'revealed_at'
        ]
        read_only_fields = fields


# ============================================================================
# Guess Serializers
# ============================================================================

class TuneTriviaGuessSerializer(serializers.ModelSerializer):
    """Serializer for guess data."""
    player_name = serializers.CharField(source='player.display_name', read_only=True)

    class Meta:
        model = TuneTriviaGuess
        fields = [
            'id', 'player', 'player_name',
            'song_guess', 'artist_guess',
            'song_correct', 'artist_correct', 'points_earned',
            'submitted_at'
        ]
        read_only_fields = ['id', 'player', 'song_correct', 'artist_correct', 'points_earned', 'submitted_at']


class SubmitGuessSerializer(serializers.Serializer):
    """Input serializer for submitting a guess."""
    song_guess = serializers.CharField(max_length=300, required=False, allow_blank=True, allow_null=True)
    artist_guess = serializers.CharField(max_length=300, required=False, allow_blank=True, allow_null=True)


# ============================================================================
# Session Serializers
# ============================================================================

class TuneTriviaSessionListSerializer(serializers.ModelSerializer):
    """Serializer for session list view."""
    host_username = serializers.CharField(source='host.username', read_only=True)
    player_count = serializers.SerializerMethodField()
    round_count = serializers.SerializerMethodField()

    class Meta:
        model = TuneTriviaSession
        fields = [
            'id', 'name', 'code', 'host_username', 'mode', 'status',
            'max_songs', 'seconds_per_song', 'enable_trivia',
            'player_count', 'round_count', 'created_at'
        ]
        read_only_fields = fields

    def get_player_count(self, obj):
        return obj.players.count()

    def get_round_count(self, obj):
        return obj.rounds.count()


class TuneTriviaSessionDetailSerializer(TuneTriviaSessionListSerializer):
    """Serializer for session detail view with nested players and rounds."""
    players = TuneTriviaPlayerSerializer(many=True, read_only=True)
    rounds = TuneTriviaRoundSerializer(many=True, read_only=True)

    class Meta(TuneTriviaSessionListSerializer.Meta):
        fields = TuneTriviaSessionListSerializer.Meta.fields + ['players', 'rounds']


class CreateSessionSerializer(serializers.Serializer):
    """Input serializer for creating a session."""
    name = serializers.CharField(max_length=100)
    mode = serializers.ChoiceField(choices=TuneTriviaSession.Mode.choices, default='party')
    max_songs = serializers.IntegerField(min_value=1, max_value=50, default=10)
    seconds_per_song = serializers.IntegerField(min_value=10, max_value=120, default=30)
    enable_trivia = serializers.BooleanField(default=True)
    auto_select_decade = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    auto_select_genre = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    auto_select_artist = serializers.CharField(max_length=200, required=False, allow_blank=True, allow_null=True)


class JoinSessionSerializer(serializers.Serializer):
    """Input serializer for joining a session."""
    code = serializers.CharField(max_length=6)
    display_name = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)


# ============================================================================
# Track Serializers
# ============================================================================

class AddTrackSerializer(serializers.Serializer):
    """Input serializer for adding a track to a session."""
    track_id = serializers.CharField(max_length=100)


# ============================================================================
# Scoring Serializers
# ============================================================================

class AwardPointsSerializer(serializers.Serializer):
    """Input serializer for awarding points (Host Mode)."""
    points = serializers.IntegerField(min_value=0, max_value=1000)


# ============================================================================
# Leaderboard Serializers
# ============================================================================

class LeaderboardEntrySerializer(serializers.ModelSerializer):
    """Serializer for leaderboard entries."""

    class Meta:
        model = TuneTriviaLeaderboardEntry
        fields = [
            'id', 'display_name', 'total_score', 'total_games',
            'total_correct_songs', 'total_correct_artists', 'last_played_at'
        ]
        read_only_fields = fields
