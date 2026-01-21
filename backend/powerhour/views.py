from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import Track

from .models import PowerHourSession, SessionPlayer, SessionTrack
from .serializers import (
    AddTrackSerializer,
    CreateSessionSerializer,
    ImportSessionTracksSerializer,
    JoinSessionSerializer,
    SessionDetailSerializer,
    SessionListSerializer,
    SessionPlayerSerializer,
    SessionStateSerializer,
    SessionTrackSerializer,
    UpdateSessionSerializer,
)


class IsSessionAdmin:
    """Mixin to check if the requesting user is the session admin."""

    def _check_admin(self, request, session):
        if session.admin != request.user:
            return Response(
                {'detail': 'Only the session admin can perform this action.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None


class SessionViewSet(viewsets.ModelViewSet, IsSessionAdmin):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = None
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateSessionSerializer
        if self.action in ('partial_update', 'update'):
            return UpdateSessionSerializer
        if self.action == 'retrieve':
            return SessionDetailSerializer
        return SessionListSerializer

    def get_queryset(self):
        user = self.request.user
        return PowerHourSession.objects.filter(
            Q(admin=user) | Q(players__user=user)
        ).distinct()

    def perform_create(self, serializer):
        session = serializer.save(admin=self.request.user)
        # Add the creator as a player with admin flag
        SessionPlayer.objects.create(
            session=session,
            user=self.request.user,
            is_admin=True,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Return full session detail
        output = SessionListSerializer(serializer.instance)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        session = self.get_object()
        admin_check = self._check_admin(request, session)
        if admin_check:
            return admin_check
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        session = self.get_object()
        admin_check = self._check_admin(request, session)
        if admin_check:
            return admin_check
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        session = self.get_object()
        admin_check = self._check_admin(request, session)
        if admin_check:
            return admin_check
        return super().destroy(request, *args, **kwargs)

    # --- Join ---

    @action(detail=False, methods=['post'], url_path='join')
    def join(self, request):
        serializer = JoinSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['invite_code']

        try:
            session = PowerHourSession.objects.get(invite_code=code)
        except PowerHourSession.DoesNotExist:
            return Response(
                {'detail': 'Invalid invite code.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if session.status == 'ended':
            return Response(
                {'detail': 'This session has already ended.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _, created = SessionPlayer.objects.get_or_create(
            session=session,
            user=request.user,
            defaults={'is_admin': False},
        )

        output = SessionListSerializer(session)
        return Response(output.data, status=status.HTTP_200_OK)

    # --- Playback Controls ---

    @action(detail=True, methods=['post'], url_path='start')
    def start(self, request, id=None):
        session = self.get_object()
        admin_check = self._check_admin(request, session)
        if admin_check:
            return admin_check

        if session.status != 'lobby':
            return Response(
                {'detail': 'Session can only be started from lobby.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if session.tracks.count() == 0:
            return Response(
                {'detail': 'Add at least one track before starting.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.status = 'active'
        session.current_track_index = 0
        session.started_at = timezone.now()
        session.save()

        return Response(SessionStateSerializer(session).data)

    @action(detail=True, methods=['post'], url_path='pause')
    def pause(self, request, id=None):
        session = self.get_object()
        admin_check = self._check_admin(request, session)
        if admin_check:
            return admin_check

        if session.status != 'active':
            return Response(
                {'detail': 'Can only pause an active session.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.status = 'paused'
        session.save()
        return Response(SessionStateSerializer(session).data)

    @action(detail=True, methods=['post'], url_path='resume')
    def resume(self, request, id=None):
        session = self.get_object()
        admin_check = self._check_admin(request, session)
        if admin_check:
            return admin_check

        if session.status != 'paused':
            return Response(
                {'detail': 'Can only resume a paused session.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.status = 'active'
        session.save()
        return Response(SessionStateSerializer(session).data)

    @action(detail=True, methods=['post'], url_path='end')
    def end(self, request, id=None):
        session = self.get_object()
        admin_check = self._check_admin(request, session)
        if admin_check:
            return admin_check

        if session.status == 'ended':
            return Response(
                {'detail': 'Session already ended.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.status = 'ended'
        session.ended_at = timezone.now()
        session.save()
        return Response(SessionStateSerializer(session).data)

    @action(detail=True, methods=['post'], url_path='next')
    def next_track(self, request, id=None):
        session = self.get_object()
        admin_check = self._check_admin(request, session)
        if admin_check:
            return admin_check

        if session.status != 'active':
            return Response(
                {'detail': 'Session must be active to skip tracks.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_tracks = session.tracks.count()
        next_index = session.current_track_index + 1

        if next_index >= total_tracks:
            session.status = 'ended'
            session.ended_at = timezone.now()
        else:
            session.current_track_index = next_index

        session.save()
        return Response(SessionStateSerializer(session).data)

    # --- Tracks ---

    @action(detail=True, methods=['get', 'post'], url_path='tracks')
    def tracks_list(self, request, id=None):
        session = self.get_object()

        if request.method == 'GET':
            tracks = session.tracks.select_related('track', 'track__album', 'added_by')
            serializer = SessionTrackSerializer(tracks, many=True)
            return Response(serializer.data)

        # POST - add track
        serializer = AddTrackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        track_id = serializer.validated_data['track_id']
        start_offset = serializer.validated_data.get('start_offset_ms', 0)

        try:
            track = Track.objects.get(pk=track_id)
        except Track.DoesNotExist:
            return Response(
                {'detail': 'Track not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if session.tracks.count() >= session.max_tracks:
            return Response(
                {'detail': f'Session is at maximum capacity ({session.max_tracks} tracks).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if session.tracks.filter(track=track).exists():
            return Response(
                {'detail': 'Track already in this session.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check per-player limit
        user_track_count = session.tracks.filter(added_by=request.user).count()
        if user_track_count >= session.tracks_per_player:
            return Response(
                {'detail': f'You can only add {session.tracks_per_player} tracks.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        next_order = (session.tracks.order_by('-order').first().order + 1
                      if session.tracks.exists() else 0)

        session_track = SessionTrack.objects.create(
            session=session,
            added_by=request.user,
            track=track,
            order=next_order,
            start_offset_ms=start_offset,
        )

        output = SessionTrackSerializer(session_track)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path=r'tracks/(?P<track_pk>[^/.]+)')
    def track_remove(self, request, id=None, track_pk=None):
        session = self.get_object()

        try:
            session_track = session.tracks.get(pk=track_pk)
        except SessionTrack.DoesNotExist:
            return Response(
                {'detail': 'Track not found in this session.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Allow admin or the user who added the track to remove it
        if session.admin != request.user and session_track.added_by != request.user:
            return Response(
                {'detail': 'You can only remove tracks you added.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        session_track.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='tracks/import-session')
    def import_session_tracks(self, request, id=None):
        session = self.get_object()
        serializer = ImportSessionTracksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        source_id = serializer.validated_data['source_session_id']
        try:
            source = PowerHourSession.objects.get(pk=source_id)
        except PowerHourSession.DoesNotExist:
            return Response(
                {'detail': 'Source session not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        source_tracks = source.tracks.all()
        added = 0
        next_order = (session.tracks.order_by('-order').first().order + 1
                      if session.tracks.exists() else 0)

        for st in source_tracks:
            if session.tracks.count() >= session.max_tracks:
                break
            if session.tracks.filter(track=st.track).exists():
                continue
            SessionTrack.objects.create(
                session=session,
                added_by=request.user,
                track=st.track,
                order=next_order,
                start_offset_ms=st.start_offset_ms,
            )
            next_order += 1
            added += 1

        return Response({'imported': added}, status=status.HTTP_200_OK)

    # --- Players ---

    @action(detail=True, methods=['get'], url_path='players')
    def players_list(self, request, id=None):
        session = self.get_object()
        players = session.players.select_related('user', 'user__music_profile')
        serializer = SessionPlayerSerializer(players, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['delete'], url_path=r'players/(?P<player_pk>[^/.]+)')
    def player_remove(self, request, id=None, player_pk=None):
        session = self.get_object()
        admin_check = self._check_admin(request, session)
        if admin_check:
            return admin_check

        try:
            player = session.players.get(pk=player_pk)
        except SessionPlayer.DoesNotExist:
            return Response(
                {'detail': 'Player not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if player.user == request.user:
            return Response(
                {'detail': 'Cannot remove yourself.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        player.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- State Polling ---

    @action(detail=True, methods=['get'], url_path='state')
    def state(self, request, id=None):
        session = self.get_object()
        return Response(SessionStateSerializer(session).data)
