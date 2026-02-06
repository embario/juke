import logging

from django.db import transaction
from rest_framework import serializers

from catalog.models import MusicResource, Genre, Artist, Album, Track, SearchHistory, SearchHistoryResource

logger = logging.getLogger(__name__)


class GenreSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Genre
        fields = "__all__"


class ArtistSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Artist
        fields = "__all__"


class AlbumSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Album
        fields = "__all__"


class TrackSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Track
        fields = "__all__"


class SpotifyResourceSerializer(serializers.HyperlinkedModelSerializer):
    id = serializers.CharField(write_only=True, required=True)
    pk = serializers.IntegerField(read_only=True)
    type = serializers.CharField(write_only=True)
    uri = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = MusicResource
        fields = "__all__"


class SpotifyArtistSerializer(SpotifyResourceSerializer):
    popularity = serializers.IntegerField(write_only=True)
    followers = serializers.JSONField(write_only=True)
    genres = serializers.ListField(write_only=True, allow_empty=True)
    images = serializers.ListField(write_only=True, allow_empty=True)

    class Meta:
        model = Artist
        fields = "__all__"

    def create(self, validated_data):
        with transaction.atomic():
            instance, created = Artist.objects.update_or_create(
                spotify_id=validated_data['id'],
                defaults={'name': validated_data['name']},
            )
            if created:
                logger.info(f"Artist '{instance.name}' created.")
            else:
                logger.debug(f"Artist '{instance.name}' updated.")

            # Add Genres
            genres = []
            for genre_name in validated_data['genres']:
                genre, _ = Genre.objects.get_or_create(
                    name=genre_name,
                    spotify_id=f"genre-{genre_name}",
                )
                genres.append(genre)
            instance.genres.set(genres)

            # Add other Spotify Data
            instance.spotify_data = {
                'type': validated_data['type'],
                'uri': validated_data['uri'],
                'popularity': validated_data['popularity'],
                'followers': validated_data['followers']['total'],
                'images': [d['url'] for d in validated_data['images']],
                'genres': validated_data['genres'],
            }

            instance.save()
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['genres'] = list(instance.genres.values_list('name', flat=True))
        return data


class SpotifyAlbumSerializer(SpotifyResourceSerializer):
    album_type = serializers.CharField(required=True)
    images = serializers.ListField(write_only=True, allow_empty=True)
    artists = serializers.ListField(write_only=True, allow_empty=False)
    release_date = serializers.CharField(write_only=True)
    release_date_precision = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Album
        fields = "__all__"

    def create(self, validated_data):
        with transaction.atomic():
            instance, created = Album.get_or_create_with_validated_data(data=validated_data)
            if created:
                logger.info(f"Album '{instance.name}' created.")
            else:
                logger.debug(f"Album '{instance.name}' updated.")

            # Add Artists
            for artist_data in validated_data['artists']:
                artist, _ = Artist.objects.get_or_create(
                    name=artist_data['name'],
                    spotify_id=artist_data['id'],
                )
                instance.artists.add(artist)

            # Add other Spotify Data
            instance.spotify_data = {
                'type': validated_data['type'],
                'uri': validated_data['uri'],
                'images': [d['url'] for d in validated_data['images']],
            }

            instance.save()
        return instance


class SpotifyTrackSerializer(SpotifyResourceSerializer):
    album = serializers.JSONField(write_only=True)
    album_link = serializers.HyperlinkedRelatedField(view_name='album-detail', read_only=True, many=False)
    preview_url = serializers.URLField(write_only=True, required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = Track
        fields = "__all__"

    def create(self, validated_data):
        with transaction.atomic():
            album, album_created = Album.get_or_create_with_validated_data(
                data=validated_data['album']
            )
            if album_created:
                logger.info(f"Album '{album.name}' created.")
            else:
                logger.debug(f"Album '{album.name}' updated.")

            instance, track_created = Track.get_or_create_with_validated_data(album=album, data=validated_data)
            if track_created:
                logger.info(f"Track '{instance.name}' created.")
            else:
                logger.debug(f"Track '{instance.name}' updated.")

            # Add other Spotify Data
            instance.spotify_data = {
                'id': validated_data['id'],
                'type': validated_data['type'],
                'uri': validated_data['uri'],
                'preview_url': validated_data.get('preview_url') or '',
            }

            instance.save()
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['album_name'] = instance.album.name if instance.album else ''
        if instance.album:
            data['artist_names'] = ', '.join(a.name for a in instance.album.artists.all())
        else:
            data['artist_names'] = ''
        return data


class GenreDetailSerializer(GenreSerializer):
    description = serializers.CharField(read_only=True, required=False, allow_blank=True)
    top_artists = serializers.SerializerMethodField()

    class Meta:
        model = Genre
        fields = "__all__"

    def get_top_artists(self, obj):
        artists = getattr(obj, 'top_artists', [])
        serializer = ArtistSerializer(artists, many=True, context=self.context)
        return serializer.data


class ArtistDetailSerializer(ArtistSerializer):
    genres = serializers.SerializerMethodField()
    bio = serializers.CharField(read_only=True, required=False, allow_blank=True)
    albums = serializers.SerializerMethodField()
    top_tracks = serializers.SerializerMethodField()
    related_artists = serializers.SerializerMethodField()

    class Meta:
        model = Artist
        fields = "__all__"

    def get_genres(self, obj):
        genres = obj.genres.all()
        serializer = GenreSerializer(genres, many=True, context=self.context)
        return serializer.data

    def get_albums(self, obj):
        albums = getattr(obj, '_enriched_albums', [])
        serializer = AlbumSerializer(albums, many=True, context=self.context)
        return serializer.data

    def get_top_tracks(self, obj):
        tracks = getattr(obj, '_enriched_top_tracks', [])
        serializer = TrackSerializer(tracks, many=True, context=self.context)
        return serializer.data

    def get_related_artists(self, obj):
        artists = getattr(obj, '_enriched_related_artists', [])
        serializer = ArtistSerializer(artists, many=True, context=self.context)
        return serializer.data


class AlbumDetailSerializer(AlbumSerializer):
    description = serializers.CharField(read_only=True, required=False, allow_blank=True)
    tracks = serializers.SerializerMethodField()
    related_albums = serializers.SerializerMethodField()

    class Meta:
        model = Album
        fields = "__all__"

    def get_tracks(self, obj):
        tracks = getattr(obj, '_enriched_tracks', [])
        serializer = TrackSerializer(tracks, many=True, context=self.context)
        return serializer.data

    def get_related_albums(self, obj):
        albums = getattr(obj, '_enriched_related_albums', [])
        serializer = AlbumSerializer(albums, many=True, context=self.context)
        return serializer.data


class PlaybackProviderSerializer(serializers.Serializer):
    provider = serializers.CharField(required=False, allow_blank=True)
    device_id = serializers.CharField(required=False, allow_blank=True)


class PlayRequestSerializer(PlaybackProviderSerializer):
    track_uri = serializers.CharField(required=False, allow_blank=True)
    context_uri = serializers.CharField(required=False, allow_blank=True)
    position_ms = serializers.IntegerField(required=False, min_value=0)

    def validate(self, attrs):
        track_uri = attrs.get('track_uri')
        context_uri = attrs.get('context_uri')
        if track_uri:
            attrs['track_uri'] = track_uri.strip()
        if context_uri:
            attrs['context_uri'] = context_uri.strip()
        if attrs.get('device_id'):
            attrs['device_id'] = attrs['device_id'].strip()
        return attrs


class PlaybackStateQuerySerializer(serializers.Serializer):
    provider = serializers.CharField(required=False, allow_blank=True)


class SeekRequestSerializer(PlaybackProviderSerializer):
    position_ms = serializers.IntegerField(required=True, min_value=0)

    def validate(self, attrs):
        if attrs.get('device_id'):
            attrs['device_id'] = attrs['device_id'].strip()
        return attrs


class SearchHistoryResourceSerializer(serializers.ModelSerializer):
    """
    Serializer for individual resources engaged during a search session.
    """
    class Meta:
        model = SearchHistoryResource
        fields = ['resource_type', 'resource_id', 'resource_name']

    def validate_resource_type(self, value):
        """Ensure resource_type is one of the allowed choices."""
        valid_types = [choice[0] for choice in SearchHistoryResource.RESOURCE_TYPE_CHOICES]
        if value not in valid_types:
            raise serializers.ValidationError(
                f"Invalid resource_type. Must be one of: {', '.join(valid_types)}"
            )
        return value


class SearchHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for creating search history entries with engaged resources.
    """
    engaged_resources = SearchHistoryResourceSerializer(many=True)

    class Meta:
        model = SearchHistory
        fields = ['search_query', 'engaged_resources', 'timestamp']
        read_only_fields = ['timestamp']

    def validate_search_query(self, value):
        """Ensure search query is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("Search query cannot be empty.")
        return value.strip()

    def create(self, validated_data):
        """Create SearchHistory and associated SearchHistoryResource entries."""
        engaged_resources_data = validated_data.pop('engaged_resources')

        # Create the search history entry
        search_history = SearchHistory.objects.create(
            user=self.context['request'].user,
            search_query=validated_data['search_query']
        )

        # Create associated resources
        for resource_data in engaged_resources_data:
            SearchHistoryResource.objects.create(
                search_history=search_history,
                **resource_data
            )

        return search_history
