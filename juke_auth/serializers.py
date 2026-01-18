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
            'created_at',
            'modified_at',
            'is_owner',
        ]
        read_only_fields = ['id', 'username', 'created_at', 'modified_at', 'is_owner']

    def get_is_owner(self, obj):
        request = self.context.get('request')
        if not request or request.user.is_anonymous:
            return False
        return obj.user_id == request.user.id


class MusicProfileSearchSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username')

    class Meta:
        model = MusicProfile
        fields = ['username', 'display_name', 'tagline', 'avatar_url']
