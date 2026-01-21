from rest_framework import serializers

from .models import PowerHourSession, SessionPlayer, SessionTrack


class PlayerUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, obj):
        profile = getattr(obj, 'music_profile', None)
        if profile and profile.display_name:
            return profile.display_name
        return None


class SessionPlayerSerializer(serializers.ModelSerializer):
    user = PlayerUserSerializer(read_only=True)

    class Meta:
        model = SessionPlayer
        fields = ['id', 'user', 'is_admin', 'joined_at']
        read_only_fields = ['id', 'joined_at']


class SessionTrackSerializer(serializers.ModelSerializer):
    track_name = serializers.CharField(source='track.name', read_only=True)
    track_artist = serializers.SerializerMethodField()
    track_album = serializers.CharField(source='track.album.name', read_only=True)
    duration_ms = serializers.IntegerField(source='track.duration_ms', read_only=True)
    spotify_id = serializers.CharField(source='track.spotify_id', read_only=True)
    preview_url = serializers.SerializerMethodField()
    added_by_username = serializers.CharField(source='added_by.username', read_only=True)

    class Meta:
        model = SessionTrack
        fields = [
            'id', 'track_id', 'order', 'start_offset_ms', 'added_at',
            'track_name', 'track_artist', 'track_album', 'duration_ms',
            'spotify_id', 'preview_url', 'added_by', 'added_by_username',
        ]
        read_only_fields = ['id', 'added_at', 'added_by']

    def get_track_artist(self, obj):
        album = obj.track.album
        artists = album.artists.all() if hasattr(album, 'artists') else []
        return ', '.join(a.name for a in artists) if artists else ''

    def get_preview_url(self, obj):
        spotify_data = obj.track.spotify_data or {}
        return spotify_data.get('preview_url') or None


class SessionListSerializer(serializers.ModelSerializer):
    player_count = serializers.SerializerMethodField()
    track_count = serializers.SerializerMethodField()

    class Meta:
        model = PowerHourSession
        fields = [
            'id', 'title', 'invite_code', 'status',
            'tracks_per_player', 'max_tracks', 'seconds_per_track',
            'transition_clip', 'hide_track_owners',
            'current_track_index', 'created_at', 'started_at', 'ended_at',
            'admin', 'player_count', 'track_count',
        ]
        read_only_fields = ['id', 'invite_code', 'status', 'current_track_index',
                           'created_at', 'started_at', 'ended_at', 'admin']

    def get_player_count(self, obj):
        return obj.players.count()

    def get_track_count(self, obj):
        return obj.tracks.count()


class SessionDetailSerializer(SessionListSerializer):
    players = SessionPlayerSerializer(many=True, read_only=True)

    class Meta(SessionListSerializer.Meta):
        fields = SessionListSerializer.Meta.fields + ['players']


class CreateSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PowerHourSession
        fields = [
            'title', 'tracks_per_player', 'max_tracks',
            'seconds_per_track', 'transition_clip', 'hide_track_owners',
        ]


class UpdateSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PowerHourSession
        fields = [
            'title', 'tracks_per_player', 'max_tracks',
            'seconds_per_track', 'transition_clip', 'hide_track_owners',
        ]
        extra_kwargs = {field: {'required': False} for field in fields}


class JoinSessionSerializer(serializers.Serializer):
    invite_code = serializers.CharField(max_length=8)


class AddTrackSerializer(serializers.Serializer):
    track_id = serializers.IntegerField()
    start_offset_ms = serializers.IntegerField(default=0, min_value=0)


class ImportSessionTracksSerializer(serializers.Serializer):
    source_session_id = serializers.UUIDField()


class SessionStateSerializer(serializers.ModelSerializer):
    player_count = serializers.SerializerMethodField()
    track_count = serializers.SerializerMethodField()

    class Meta:
        model = PowerHourSession
        fields = [
            'status', 'current_track_index', 'started_at',
            'player_count', 'track_count',
        ]

    def get_player_count(self, obj):
        return obj.players.count()

    def get_track_count(self, obj):
        return obj.tracks.count()
