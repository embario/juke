from rest_framework import serializers

from juke_auth.models import JukeUser, MusicProfile


class JukeUserSerializer(serializers.HyperlinkedModelSerializer):
    token = serializers.CharField(source='auth_token.key')

    class Meta:
        model = JukeUser
        fields = ['url', 'username', 'email', 'groups', 'is_active', 'token']


class MusicProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    is_owner = serializers.SerializerMethodField()
    top_genre = serializers.SerializerMethodField()

    class Meta:
        model = MusicProfile
        fields = [
            'id',
            'username',
            'name',
            'display_name',
            'tagline',
            'bio',
            'location',
            'avatar_url',
            'favorite_genres',
            'favorite_artists',
            'favorite_albums',
            'favorite_tracks',
            'onboarding_completed_at',
            'city_lat',
            'city_lng',
            'custom_data',
            'clout',
            'top_genre',
            'created_at',
            'modified_at',
            'is_owner',
        ]
        read_only_fields = ['id', 'username', 'created_at', 'modified_at', 'is_owner', 'clout', 'top_genre']

    def get_is_owner(self, obj):
        request = self.context.get('request')
        if not request or request.user.is_anonymous:
            return False
        return obj.user_id == request.user.id

    def get_top_genre(self, obj):
        genres = obj.favorite_genres
        if genres and isinstance(genres, list) and len(genres) > 0:
            return genres[0]
        return None


class MusicProfileSearchSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username')

    class Meta:
        model = MusicProfile
        fields = ['username', 'display_name', 'tagline', 'avatar_url']


class GlobePointSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    lat = serializers.FloatField(source='city_lat')
    lng = serializers.FloatField(source='city_lng')
    top_genre = serializers.SerializerMethodField()

    class Meta:
        model = MusicProfile
        fields = ['id', 'username', 'lat', 'lng', 'clout', 'top_genre', 'display_name']

    def get_top_genre(self, obj):
        genres = obj.favorite_genres
        if genres and isinstance(genres, list) and len(genres) > 0:
            return genres[0]
        return 'other'
