import logging

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from catalog.models import MusicResource, Genre, Artist, Album, Track, SearchHistory, SearchHistoryResource
from catalog.services.provider_cache import record_provider_identity

logger = logging.getLogger(__name__)


class ProviderIdentifierSerializer(serializers.Serializer):
    source = serializers.CharField()
    external_id = serializers.CharField()
    provider_url = serializers.URLField(allow_blank=True)
    market = serializers.CharField(allow_blank=True)
    last_refreshed_at = serializers.DateTimeField(allow_null=True)
    cache_expires_at = serializers.DateTimeField(allow_null=True)


class ProviderIdentitySerializer(serializers.HyperlinkedModelSerializer):
    pk = serializers.IntegerField(read_only=True)
    provider_identifiers = serializers.SerializerMethodField()

    def get_provider_identifiers(self, obj):
        return ProviderIdentifierSerializer(obj.external_ids.all(), many=True).data


class GenreSerializer(ProviderIdentitySerializer):
    class Meta:
        model = Genre
        fields = "__all__"


class ArtistSerializer(ProviderIdentitySerializer):
    class Meta:
        model = Artist
        fields = "__all__"


class AlbumSerializer(ProviderIdentitySerializer):
    class Meta:
        model = Album
        fields = "__all__"


class TrackSerializer(ProviderIdentitySerializer):
    class Meta:
        model = Track
        fields = "__all__"


class SpotifyResourceSerializer(serializers.HyperlinkedModelSerializer):
    id = serializers.CharField(write_only=True, required=True)
    pk = serializers.IntegerField(read_only=True)
    type = serializers.CharField(write_only=True)
    uri = serializers.CharField(write_only=True, required=True)
    provider = serializers.SerializerMethodField(read_only=True)
    external_id = serializers.SerializerMethodField(read_only=True)
    provider_url = serializers.SerializerMethodField(read_only=True)
    cache_expires_at = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MusicResource
        fields = "__all__"

    def _provider_identity(self, instance):
        return instance.external_ids.filter(source='spotify').first()

    def get_provider(self, instance):
        return 'spotify'

    def get_external_id(self, instance):
        return instance.spotify_id

    def get_provider_url(self, instance):
        identity = self._provider_identity(instance)
        return identity.provider_url if identity else ''

    def get_cache_expires_at(self, instance):
        identity = self._provider_identity(instance)
        return identity.cache_expires_at if identity else None

    def _record_provider_identity(self, instance, resource_type, provider_data):
        ttl_seconds = getattr(settings, 'CATALOG_PROVIDER_CACHE_TTL_SECONDS', 86400)
        return record_provider_identity(
            instance,
            resource_type=resource_type,
            provider='spotify',
            external_id=instance.spotify_id,
            provider_data=provider_data,
            provider_url=f'https://open.spotify.com/{resource_type}/{instance.spotify_id}',
            market=self.context.get('market', ''),
            ttl_seconds=ttl_seconds,
        )


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
            self._record_provider_identity(instance, 'artist', instance.spotify_data)
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
                record_provider_identity(
                    artist,
                    resource_type='artist',
                    provider='spotify',
                    external_id=artist_data['id'],
                    provider_url=f"https://open.spotify.com/artist/{artist_data['id']}",
                    market=self.context.get('market', ''),
                    ttl_seconds=getattr(settings, 'CATALOG_PROVIDER_CACHE_TTL_SECONDS', 86400),
                )
                instance.artists.add(artist)

            # Add other Spotify Data
            instance.spotify_data = {
                'type': validated_data['type'],
                'uri': validated_data['uri'],
                'images': [d['url'] for d in validated_data['images']],
            }

            instance.save()
            self._record_provider_identity(instance, 'album', instance.spotify_data)
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
            album_data = validated_data['album']
            album, album_created = Album.get_or_create_with_validated_data(
                data=album_data
            )
            if album_created:
                logger.info(f"Album '{album.name}' created.")
            else:
                logger.debug(f"Album '{album.name}' updated.")

            # Track search responses embed the album rather than passing through
            # SpotifyAlbumSerializer. Preserve its artists and artwork so clients
            # can render complete results immediately.
            artists = []
            for artist_data in album_data.get('artists', []):
                artist, _ = Artist.objects.get_or_create(
                    name=artist_data['name'],
                    spotify_id=artist_data['id'],
                )
                record_provider_identity(
                    artist,
                    resource_type='artist',
                    provider='spotify',
                    external_id=artist_data['id'],
                    provider_url=f"https://open.spotify.com/artist/{artist_data['id']}",
                    market=self.context.get('market', ''),
                    ttl_seconds=getattr(settings, 'CATALOG_PROVIDER_CACHE_TTL_SECONDS', 86400),
                )
                artists.append(artist)
            if artists:
                album.artists.set(artists)
            album.spotify_data = {
                'type': album_data.get('type', 'album'),
                'uri': album_data.get('uri', f"spotify:album:{album_data['id']}"),
                'images': [image['url'] for image in album_data.get('images', []) if image.get('url')],
            }
            album.save(update_fields=['spotify_data'])
            record_provider_identity(
                album,
                resource_type='album',
                provider='spotify',
                external_id=album.spotify_id,
                provider_data=album.spotify_data,
                provider_url=f'https://open.spotify.com/album/{album.spotify_id}',
                market=self.context.get('market', ''),
                ttl_seconds=getattr(settings, 'CATALOG_PROVIDER_CACHE_TTL_SECONDS', 86400),
            )

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
            self._record_provider_identity(instance, 'track', instance.spotify_data)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['album_name'] = instance.album.name if instance.album else ''
        if instance.album:
            data['artist_names'] = ', '.join(a.name for a in instance.album.artists.all())
            images = (instance.album.spotify_data or {}).get('images') or []
            data['artwork_url'] = images[0] if images else None
        else:
            data['artist_names'] = ''
            data['artwork_url'] = None
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
    offset_uri = serializers.CharField(required=False, allow_blank=True)
    offset_position = serializers.IntegerField(required=False, min_value=0)
    position_ms = serializers.IntegerField(required=False, min_value=0)

    def validate(self, attrs):
        track_uri = attrs.get('track_uri')
        context_uri = attrs.get('context_uri')
        offset_uri = attrs.get('offset_uri')
        offset_position = attrs.get('offset_position')
        if track_uri:
            attrs['track_uri'] = track_uri.strip()
        if context_uri:
            attrs['context_uri'] = context_uri.strip()
        if offset_uri:
            attrs['offset_uri'] = offset_uri.strip()
        if attrs.get('device_id'):
            attrs['device_id'] = attrs['device_id'].strip()
        if (offset_uri or offset_position is not None) and not attrs.get('context_uri'):
            raise serializers.ValidationError('offset_uri and offset_position require context_uri.')
        if offset_uri and offset_position is not None:
            raise serializers.ValidationError('Only one of offset_uri or offset_position can be provided.')
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
