import logging

from django.db import transaction
from rest_framework import serializers

from catalog.models import MusicResource, Genre, Artist, Album, Track

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
            instance, created = Artist.objects.get_or_create(
                name=validated_data['name'],
                spotify_id=validated_data['id'],
            )
            action = "created" if created else "updated"
            logger.info(f"Artist '{instance.name}' {action}.")

            # Add Genres
            for genre_name in validated_data['genres']:
                genre, _ = Genre.objects.get_or_create(
                    name=genre_name,
                    spotify_id=f"genre-{genre_name}",
                )
                instance.genres.add(genre)

            # Add other Spotify Data
            instance.spotify_data = {
                'type': validated_data['type'],
                'uri': validated_data['uri'],
                'popularity': validated_data['popularity'],
                'followers': validated_data['followers']['total'],
                'images': [d['url'] for d in validated_data['images']],
            }

            instance.save()
        return instance


class SpotifyAlbumSerializer(SpotifyResourceSerializer):
    album_type = serializers.CharField(required=True)
    images = serializers.ListField(write_only=True, allow_empty=True)
    artists = serializers.ListField(write_only=True, allow_empty=False)

    class Meta:
        model = Album
        fields = "__all__"

    def create(self, validated_data):
        with transaction.atomic():
            instance, created = Album.get_or_create_with_validated_data(data=validated_data)
            action = "created" if created else "updated"
            logger.info(f"Album '{instance.name}' {action}.")

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
            action = "created" if album_created else "updated"
            logger.info(f"Album '{album.name}' {action}.")

            instance, track_created = Track.get_or_create_with_validated_data(album=album, data=validated_data)
            action = "created" if track_created else "updated"
            logger.info(f"Track '{instance.name}' {action}.")

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
