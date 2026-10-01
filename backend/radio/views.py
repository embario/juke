"""Authenticated, user-scoped radio API for the Juke app (contract: tasks/juke-app-implementation.md)."""
import logging

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.services.playback import PlaybackError, PlaybackProviderFailure, PlaybackService
from radio import frequencies
from radio.models import (EXCLUSION_SCOPE_EVERYWHERE, QUEUED_EVENT, STATION_KIND_CUSTOM, STATION_KIND_PERSONAL, Exclusion,
                          ListeningEvent, Station, TrackReaction)
from radio.payloads import exclusion_payload, station_payload
from radio.serializers import (CrateQuerySerializer, EventSerializer, ExclusionCreateSerializer, NextSerializer, PlaySerializer,
                               ReactionsSerializer, StationCreateSerializer, StationUpdateSerializer)
from radio.services import crate, signals, spotify, suggestions
from radio.services.recommend import next_tracks
from vibe.authentication import VIBE_AUTHENTICATION_CLASSES
from rest_framework.throttling import UserRateThrottle

logger = logging.getLogger(__name__)

PERSONAL_STATION_NAME = 'My Station'
SPOTIFY_BUDGET_SECONDS = 4
MAX_NAME_LENGTH = 120


class RadioUserThrottle(UserRateThrottle):
    # Radio clients post chatty listening events; keep them off the stricter Vibe budget.
    scope = 'radio_user'


class RadioAPIView(APIView):
    authentication_classes = VIBE_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = [RadioUserThrottle]

    def validated(self, serializer_cls, data):
        serializer = serializer_cls(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def station(self, station_id):
        return get_object_or_404(Station, id=station_id, user=self.request.user)

    def optional_station(self, station_id):
        return self.station(station_id) if station_id else None


def ensure_personal_station(user):
    station = Station.objects.filter(user=user, kind=STATION_KIND_PERSONAL).first()
    if station:
        return station
    others = Station.objects.filter(user=user).values_list('frequency', flat=True)
    try:
        with transaction.atomic():
            return Station.objects.create(user=user, kind=STATION_KIND_PERSONAL, name=PERSONAL_STATION_NAME,
                                          frequency=frequencies.place(frequencies.PERSONAL_FREQUENCY, others), learning=True)
    except IntegrityError:  # concurrent first requests
        return Station.objects.get(user=user, kind=STATION_KIND_PERSONAL)


def lock_dial(user):
    """Per-user mutex for frequency placement: lock the personal station row (created first).

    ``select_for_update`` on the user's stations alone can't stop two concurrent requests from
    both choosing the same free slot, because a new station's row doesn't exist yet. Must be
    called inside a transaction.
    """
    ensure_personal_station(user)
    return Station.objects.select_for_update().get(user=user, kind=STATION_KIND_PERSONAL)


def default_name(seeds, feelings):
    if seeds:
        base = seeds[0]['title']
    else:
        base = ' '.join(feelings[:3])
    suffix = ' Radio'
    return base[:MAX_NAME_LENGTH - len(suffix)].strip() + suffix


def _user_exclusions(user):
    return list(Exclusion.objects.filter(user=user))


class StationCollectionView(RadioAPIView):
    def get(self, request):
        ensure_personal_station(request.user)
        stations = Station.objects.filter(user=request.user).select_related('user')
        exclusions = _user_exclusions(request.user)
        return Response({'stations': [station_payload(station, exclusions) for station in stations]})

    def post(self, request):
        data = self.validated(StationCreateSerializer, request.data)
        ensure_personal_station(request.user)
        with transaction.atomic():
            lock_dial(request.user)
            others = list(Station.objects.filter(user=request.user).values_list('frequency', flat=True))
            station = Station.objects.create(
                user=request.user,
                kind=STATION_KIND_CUSTOM,
                name=(data.get('name') or '').strip() or default_name(data['seeds'], data['feelings']),
                frequency=frequencies.highest_free(others),
                seeds=data['seeds'],
                feelings=data['feelings'],
            )
        return Response(station_payload(station, _user_exclusions(request.user)), status=status.HTTP_201_CREATED)


class StationDetailView(RadioAPIView):
    def get(self, request, station_id):
        return Response(station_payload(self.station(station_id), _user_exclusions(request.user)))

    def patch(self, request, station_id):
        data = self.validated(StationUpdateSerializer, request.data)
        ensure_personal_station(request.user)
        with transaction.atomic():
            lock_dial(request.user)
            station = get_object_or_404(Station.objects.select_for_update(), id=station_id, user=request.user)
            for field in ('name', 'seeds', 'feelings', 'learning'):
                if field in data:
                    setattr(station, field, data[field])
            if 'frequency' in data:
                others = Station.objects.filter(user=request.user).exclude(id=station.id).values_list('frequency', flat=True)
                station.frequency = frequencies.place(data['frequency'], others)
            station.save()
        return Response(station_payload(station, _user_exclusions(request.user)))

    def delete(self, request, station_id):
        station = self.station(station_id)
        if station.is_personal:
            return Response({'detail': 'The personal station cannot be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        station.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def add_exclusion(user, station, scope, kind, value, label=''):
    """Idempotent: re-adding the same rule returns the existing exclusion.

    Partial unique constraints back this up, so concurrent duplicates resolve to one row.
    Artist exclusions get the artist's name as label when the caller didn't send one, so
    tracks known only by artist name (MLCore evidence) are filtered too.
    """
    target = None if scope == EXCLUSION_SCOPE_EVERYWHERE else station
    lookup = {'user': user, 'station': target, 'scope': scope, 'kind': kind, 'value': value}
    if kind == 'artist' and not label:
        with spotify.budget(SPOTIFY_BUDGET_SECONDS):
            label = spotify.artist_name(value)
    exclusion = Exclusion.objects.filter(**lookup).first()
    created = False
    if exclusion is None:
        try:
            with transaction.atomic():
                exclusion = Exclusion.objects.create(**lookup, label=label)
                created = True
        except IntegrityError:  # a concurrent request created it first
            exclusion = Exclusion.objects.get(**lookup)
    if not created and label and not exclusion.label:
        exclusion.label = label
        exclusion.save(update_fields=['label'])
    return exclusion, created


def _artist_from_track(track, artist_id=''):
    """(artist id, name) for ``artist_id`` on ``track``, or its primary artist."""
    ids, names = track.get('artistIds') or [], track.get('artistNames') or []
    if artist_id and artist_id in ids:
        index = ids.index(artist_id)
        return artist_id, names[index] if index < len(names) else ''
    if artist_id:
        return artist_id, ''
    return (ids[0] if ids else track.get('artistId') or ''), (names[0] if names else '')


class StationExclusionsView(RadioAPIView):
    def post(self, request, station_id):
        station = self.station(station_id)
        data = self.validated(ExclusionCreateSerializer, request.data)
        exclusion, created = add_exclusion(request.user, station, data['scope'], data['kind'], data['value'].strip(),
                                           data['label'].strip())
        return Response(exclusion_payload(exclusion), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ExclusionDetailView(RadioAPIView):
    def delete(self, request, exclusion_id):
        get_object_or_404(Exclusion, id=exclusion_id, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReactionsView(RadioAPIView):
    def put(self, request):
        data = self.validated(ReactionsSerializer, request.data)
        station = self.optional_station(data.get('stationId'))
        reactions = data['reactions']
        track_id = data['spotifyTrackId'].strip()
        if reactions:
            TrackReaction.objects.update_or_create(user=request.user, spotify_track_id=track_id,
                                                   defaults={'reactions': reactions, 'station': station})
        else:
            TrackReaction.objects.filter(user=request.user, spotify_track_id=track_id).delete()
        stations = list(Station.objects.filter(user=request.user))
        return Response({'reactions': reactions, 'suggestion': suggestions.suggest_station(reactions, station, stations)})


class StationNextView(RadioAPIView):
    def post(self, request, station_id):
        station = self.station(station_id)
        data = self.validated(NextSerializer, request.data)
        result = next_tracks(request.user, station, count=data['count'], recent_ids=data['recentTrackIds'])
        return Response({'tracks': result.tracks, 'source': result.source})


class PlayView(RadioAPIView):
    def post(self, request):
        data = self.validated(PlaySerializer, request.data)
        station = self.station(data['stationId'])
        device_id = data.get('deviceId') or None
        # Resolve the provider before picking so an unlinked account fails fast.
        try:
            service = PlaybackService(request.user, provider='spotify')
        except PlaybackError as exc:
            return _playback_error(exc)
        result = next_tracks(request.user, station, count=1, recent_ids=data['recentTrackIds'])
        if not result.tracks:
            return Response({'detail': 'This station has nothing new to play right now.', 'code': 'radio_no_tracks'},
                            status=status.HTTP_409_CONFLICT)
        track = result.tracks[0]
        try:
            if data['mode'] == 'now':
                state = service.play(track_uri=track['uri'], context_uri=None, offset_uri=None, offset_position=None,
                                     position_ms=None, device_id=device_id)
            else:
                state = service.queue(track_uri=track['uri'], device_id=device_id)
        except PlaybackError as exc:
            return _playback_error(exc)
        ListeningEvent.objects.create(
            user=request.user, station=station, spotify_track_id=track['spotifyId'], spotify_artist_id=track.get('artistId') or '',
            event='play' if data['mode'] == 'now' else QUEUED_EVENT, source='radio')
        return Response({'track': track, 'state': state, 'source': result.source})


def _playback_error(exc):
    code = exc.get_codes() if isinstance(exc.get_codes(), str) else 'playback_error'
    http_status = status.HTTP_502_BAD_GATEWAY if isinstance(exc, PlaybackProviderFailure) else exc.status_code
    return Response({'detail': str(exc.detail), 'code': code}, status=http_status)


class EventsView(RadioAPIView):
    def post(self, request):
        data = self.validated(EventSerializer, request.data)
        station = self.optional_station(data.get('stationId'))
        track_id = data['spotifyTrackId'].strip()
        artist_id = (data.get('artistId') or '').strip()
        event = data['event']
        label = ''
        if event == 'never_artist':
            with spotify.budget(SPOTIFY_BUDGET_SECONDS):
                track = spotify.get_tracks([track_id]).get(track_id) or {}
            artist_id, label = _artist_from_track(track, artist_id)
        ListeningEvent.objects.create(user=request.user, station=station, spotify_track_id=track_id, spotify_artist_id=artist_id,
                                      event=event, position_ms=data.get('positionMs'), source=data.get('source') or '')
        # Explicit "keep out" gestures become exclusions so every later pick honours them.
        if event == 'not_on_station' and station is not None:
            add_exclusion(request.user, station, 'station', 'track', track_id)
        elif event == 'never_artist':
            if artist_id:
                add_exclusion(request.user, station, EXCLUSION_SCOPE_EVERYWHERE, 'artist', artist_id, label)
            else:
                logger.info('never_artist for %s without a resolvable artist; excluding the track instead', track_id)
                add_exclusion(request.user, station, EXCLUSION_SCOPE_EVERYWHERE, 'track', track_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CrateView(RadioAPIView):
    def get(self, request):
        data = self.validated(CrateQuerySerializer, request.query_params)
        query = data['q'].strip()
        with spotify.budget(SPOTIFY_BUDGET_SECONDS):
            items = crate.search_crate(data['kind'], query) if query else crate.personal_crate(request.user, data['kind'])
        return Response({'items': items})


class SessionSummaryView(RadioAPIView):
    def get(self, request):
        events = signals.current_session_events(request.user)
        track_ids = signals.session_song_ids(events)
        if not events or not track_ids:
            return Response({'startedAt': None, 'songCount': 0, 'reactions': [], 'tracks': []})
        reaction_rows = TrackReaction.objects.filter(user=request.user, spotify_track_id__in=track_ids,
                                                     updated_at__gte=events[0].created_at)
        reactions = list(dict.fromkeys(reaction for row in reaction_rows.order_by('updated_at') for reaction in row.reactions))
        with spotify.budget(SPOTIFY_BUDGET_SECONDS):
            hydrated = spotify.get_tracks(track_ids[:50])
        return Response({
            'startedAt': events[0].created_at.isoformat(),
            'songCount': len(track_ids),
            'reactions': reactions,
            'tracks': [hydrated.get(track_id) or minimal_track(track_id) for track_id in track_ids[:50]],
        })


def minimal_track(track_id):
    """Placeholder when Spotify can't hydrate a track right now."""
    return {'spotifyId': track_id, 'uri': f'spotify:track:{track_id}', 'title': '', 'artist': '', 'artistId': '',
            'artistIds': [], 'artistNames': [], 'album': '', 'albumId': '', 'artworkUrl': None, 'durationMs': 0}
