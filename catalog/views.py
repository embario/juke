import logging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from catalog import serializers, controller
from catalog.models import Genre, Artist, Album, Track
from catalog.tasks import sync_spotify_genres_task

log = logging.getLogger(__name__)


class MusicResourceViewSet(viewsets.ReadOnlyModelViewSet):
    def list(self, request):
        if 'external' in request.GET and bool(request.GET['external']) is True:
            log.info("RECV Request for External Source: %s", request)
            res = controller.route(request)
            return Response(res.data)
        else:
            log.info("RECV Request for Internal Data: %s", request)
        return super().list(request)

    def get_object(self):
        if 'external' in self.request.GET and bool(self.request.GET['external']) is True:
            res = controller.route(self.request)
            return res.instance
        return super().get_object()


class GenreViewSet(MusicResourceViewSet):
    queryset = Genre.objects.all()
    serializer_class = serializers.GenreSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def refresh(self, request):
        job = sync_spotify_genres_task.delay()
        return Response({'task_id': job.id}, status=status.HTTP_202_ACCEPTED)


class ArtistViewSet(MusicResourceViewSet):
    queryset = Artist.objects.all()
    serializer_class = serializers.ArtistSerializer
    permission_classes = [permissions.IsAuthenticated]


class AlbumViewSet(MusicResourceViewSet):
    queryset = Album.objects.all()
    serializer_class = serializers.AlbumSerializer
    permission_classes = [permissions.IsAuthenticated]


class TrackViewSet(MusicResourceViewSet):
    queryset = Track.objects.all()
    serializer_class = serializers.TrackSerializer
    permission_classes = [permissions.IsAuthenticated]
