import logging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from catalog import serializers, controller
from catalog.services.playback import PlaybackService
from catalog.services.featured_genres import get_featured_genres
from catalog.services.detail_enrichment import ResourceDetailService
from catalog.models import Genre, Artist, Album, Track, SearchHistory
from catalog.tasks import sync_spotify_genres_task

log = logging.getLogger(__name__)


class MusicResourceViewSet(viewsets.ReadOnlyModelViewSet):
    @staticmethod
    def _use_external_source(request):
        raw_value = request.GET.get('external')
        if raw_value is None:
            return False
        if isinstance(raw_value, bool):
            return raw_value
        return str(raw_value).lower() in ('true', '1', 'yes')

    def list(self, request):
        if self._use_external_source(request):
            log.info("RECV Request for External Source: %s", request)
            res = controller.route(request)
            return Response(res.data)
        else:
            log.info("RECV Request for Internal Data: %s", request)
        return super().list(request)

    def get_object(self):
        if self._use_external_source(self.request):
            res = controller.route(self.request)
            return res.instance
        return super().get_object()


class GenreViewSet(MusicResourceViewSet):
    queryset = Genre.objects.all()
    serializer_class = serializers.GenreSerializer
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        genre = self.get_object()
        enriched = ResourceDetailService.enrich_genre(genre)
        genre.description = enriched['description']
        genre.top_artists = enriched['top_artists']
        serializer = serializers.GenreDetailSerializer(genre, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def featured(self, request):
        payload = get_featured_genres()
        return Response(payload)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def refresh(self, request):
        job = sync_spotify_genres_task.delay()
        return Response({'task_id': job.id}, status=status.HTTP_202_ACCEPTED)


class ArtistViewSet(MusicResourceViewSet):
    queryset = Artist.objects.all()
    serializer_class = serializers.ArtistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        artist = self.get_object()
        enriched = ResourceDetailService.enrich_artist(artist)
        artist.bio = enriched['bio']
        artist._enriched_albums = enriched['albums']
        artist._enriched_top_tracks = enriched['top_tracks']
        artist._enriched_related_artists = enriched['related_artists']
        serializer = serializers.ArtistDetailSerializer(artist, context={'request': request})
        return Response(serializer.data)


class AlbumViewSet(MusicResourceViewSet):
    queryset = Album.objects.all()
    serializer_class = serializers.AlbumSerializer
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        album = self.get_object()
        enriched = ResourceDetailService.enrich_album(album)
        album.description = enriched['description']
        album._enriched_tracks = enriched['tracks']
        album._enriched_related_albums = enriched['related_albums']
        serializer = serializers.AlbumDetailSerializer(album, context={'request': request})
        return Response(serializer.data)


class TrackViewSet(MusicResourceViewSet):
    queryset = Track.objects.all()
    serializer_class = serializers.TrackSerializer
    permission_classes = [permissions.IsAuthenticated]


class PlaybackViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _validated(self, serializer_cls, data):
        serializer = serializer_cls(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _service(self, provider: str | None):
        return PlaybackService(self.request.user, provider=provider)

    def _respond(self, state, status_code=status.HTTP_200_OK):
        if state is None:
            return Response(status=status_code)
        return Response(state, status=status_code)

    @action(detail=False, methods=['post'])
    def play(self, request):
        data = self._validated(serializers.PlayRequestSerializer, request.data)
        service = self._service(data.get('provider'))
        state = service.play(
            track_uri=data.get('track_uri'),
            context_uri=data.get('context_uri'),
            position_ms=data.get('position_ms'),
            device_id=data.get('device_id'),
        )
        return self._respond(state, status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['post'])
    def pause(self, request):
        data = self._validated(serializers.PlaybackProviderSerializer, request.data)
        service = self._service(data.get('provider'))
        state = service.pause(device_id=data.get('device_id'))
        return self._respond(state)

    @action(detail=False, methods=['post'])
    def next(self, request):
        data = self._validated(serializers.PlaybackProviderSerializer, request.data)
        service = self._service(data.get('provider'))
        state = service.next(device_id=data.get('device_id'))
        return self._respond(state)

    @action(detail=False, methods=['post'])
    def previous(self, request):
        data = self._validated(serializers.PlaybackProviderSerializer, request.data)
        service = self._service(data.get('provider'))
        state = service.previous(device_id=data.get('device_id'))
        return self._respond(state)

    @action(detail=False, methods=['post'])
    def seek(self, request):
        data = self._validated(serializers.SeekRequestSerializer, request.data)
        service = self._service(data.get('provider'))
        state = service.seek(position_ms=data['position_ms'], device_id=data.get('device_id'))
        return self._respond(state)

    @action(detail=False, methods=['get'])
    def state(self, request):
        data = self._validated(serializers.PlaybackStateQuerySerializer, request.query_params)
        service = self._service(data.get('provider'))
        state = service.state()
        if state is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(state)


class SearchHistoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for creating and viewing search history.
    Users can only see their own search history.
    """
    serializer_class = serializers.SearchHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return search history for the authenticated user only."""
        return SearchHistory.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        """Create a new search history entry with engaged resources."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log.info(f"Search history created for user {request.user.username}: '{request.data.get('search_query')}'")
        return Response(serializer.data, status=status.HTTP_201_CREATED)
