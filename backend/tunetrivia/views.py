from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    TuneTriviaSession,
    TuneTriviaPlayer,
    TuneTriviaRound,
    TuneTriviaGuess,
    TuneTriviaLeaderboardEntry,
)
from .serializers import (
    TuneTriviaSessionListSerializer,
    TuneTriviaSessionDetailSerializer,
    TuneTriviaPlayerSerializer,
    TuneTriviaRoundSerializer,
    TuneTriviaRoundRevealedSerializer,
    TuneTriviaGuessSerializer,
    CreateSessionSerializer,
    JoinSessionSerializer,
    AddTrackSerializer,
    AddPlayerSerializer,
    AwardPointsSerializer,
    SubmitGuessSerializer,
    LeaderboardEntrySerializer,
)
from .services import TrackSelectionService, TriviaGenerationService


def normalize_string(s):
    """Normalize string for fuzzy matching."""
    if not s:
        return ''
    return s.lower().strip()


def fuzzy_match(guess, answer, threshold=0.7):
    """Check if guess matches answer using fuzzy matching."""
    if not guess or not answer:
        return False
    guess_norm = normalize_string(guess)
    answer_norm = normalize_string(answer)

    # Exact match
    if guess_norm == answer_norm:
        return True

    # Check if guess contains answer or vice versa
    if guess_norm in answer_norm or answer_norm in guess_norm:
        return True

    # Fuzzy match using sequence matcher
    ratio = SequenceMatcher(None, guess_norm, answer_norm).ratio()
    return ratio >= threshold


class TuneTriviaSessionViewSet(viewsets.ModelViewSet):
    """ViewSet for TuneTrivia sessions."""
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateSessionSerializer
        if self.action in ['retrieve', 'join', 'start', 'state']:
            return TuneTriviaSessionDetailSerializer
        return TuneTriviaSessionListSerializer

    def get_queryset(self):
        """Return sessions where user is host or player."""
        user = self.request.user
        return TuneTriviaSession.objects.filter(
            Q(host=user) | Q(players__user=user)
        ).distinct().prefetch_related('players', 'rounds')

    def create(self, request):
        """Create a new TuneTrivia session."""
        serializer = CreateSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            session = TuneTriviaSession.objects.create(
                name=data['name'],
                host=request.user,
                mode=data['mode'],
                max_songs=data['max_songs'],
                seconds_per_song=data['seconds_per_song'],
                enable_trivia=data['enable_trivia'],
                auto_select_decade=data.get('auto_select_decade'),
                auto_select_genre=data.get('auto_select_genre'),
                auto_select_artist=data.get('auto_select_artist'),
            )

            # Add host as a player
            display_name = request.user.username
            if hasattr(request.user, 'music_profile') and request.user.music_profile.display_name:
                display_name = request.user.music_profile.display_name

            TuneTriviaPlayer.objects.create(
                session=session,
                user=request.user,
                display_name=display_name,
                is_host=True
            )

        output = TuneTriviaSessionDetailSerializer(session, context={'request': request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='mine')
    def mine(self, request):
        """Get sessions where the current user is host or player."""
        queryset = self.get_queryset()
        serializer = TuneTriviaSessionListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='join')
    def join(self, request):
        """Join a session by invite code."""
        serializer = JoinSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['code'].upper()
        display_name = serializer.validated_data.get('display_name')

        try:
            session = TuneTriviaSession.objects.get(code=code)
        except TuneTriviaSession.DoesNotExist:
            return Response(
                {'detail': 'Session not found with that code.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if session.status == TuneTriviaSession.Status.FINISHED:
            return Response(
                {'detail': 'This session has already ended.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Determine display name
        if not display_name:
            display_name = request.user.username
            if hasattr(request.user, 'music_profile') and request.user.music_profile.display_name:
                display_name = request.user.music_profile.display_name

        # Check if already joined
        player, created = TuneTriviaPlayer.objects.get_or_create(
            session=session,
            user=request.user,
            defaults={'display_name': display_name}
        )

        output = TuneTriviaSessionDetailSerializer(session, context={'request': request})
        return Response(output.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='start')
    def start(self, request, id=None):
        """Start the game (host only)."""
        session = self.get_object()

        if session.host != request.user:
            return Response(
                {'detail': 'Only the host can start the game.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if session.status != TuneTriviaSession.Status.LOBBY:
            return Response(
                {'detail': 'Game can only be started from lobby.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if session.rounds.count() == 0:
            return Response(
                {'detail': 'Add at least one track before starting.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            session.status = TuneTriviaSession.Status.PLAYING
            session.started_at = timezone.now()
            session.save()

            # Start the first round
            first_round = session.rounds.first()
            if first_round:
                first_round.status = TuneTriviaRound.Status.PLAYING
                first_round.started_at = timezone.now()
                first_round.save()

        output = TuneTriviaSessionDetailSerializer(session, context={'request': request})
        return Response(output.data)

    @action(detail=True, methods=['post'], url_path='pause')
    def pause(self, request, id=None):
        """Pause the game (host only)."""
        session = self.get_object()

        if session.host != request.user:
            return Response(
                {'detail': 'Only the host can pause the game.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if session.status != TuneTriviaSession.Status.PLAYING:
            return Response(
                {'detail': 'Can only pause a playing game.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session.status = TuneTriviaSession.Status.PAUSED
        session.save()

        output = TuneTriviaSessionListSerializer(session, context={'request': request})
        return Response(output.data)

    @action(detail=True, methods=['post'], url_path='resume')
    def resume(self, request, id=None):
        """Resume a paused game (host only)."""
        session = self.get_object()

        if session.host != request.user:
            return Response(
                {'detail': 'Only the host can resume the game.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if session.status != TuneTriviaSession.Status.PAUSED:
            return Response(
                {'detail': 'Can only resume a paused game.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session.status = TuneTriviaSession.Status.PLAYING
        session.save()

        output = TuneTriviaSessionListSerializer(session, context={'request': request})
        return Response(output.data)

    @action(detail=True, methods=['post'], url_path='end')
    def end(self, request, id=None):
        """End the game (host only)."""
        session = self.get_object()

        if session.host != request.user:
            return Response(
                {'detail': 'Only the host can end the game.'},
                status=status.HTTP_403_FORBIDDEN
            )

        with transaction.atomic():
            session.status = TuneTriviaSession.Status.FINISHED
            session.finished_at = timezone.now()
            session.save()

            # Update leaderboard for party mode
            if session.mode == TuneTriviaSession.Mode.PARTY:
                self._update_leaderboard(session)

        output = TuneTriviaSessionListSerializer(session, context={'request': request})
        return Response(output.data)

    @action(detail=True, methods=['post'], url_path='reveal')
    def reveal(self, request, id=None):
        """Reveal the current round's answer (host only)."""
        session = self.get_object()

        if session.host != request.user:
            return Response(
                {'detail': 'Only the host can reveal answers.'},
                status=status.HTTP_403_FORBIDDEN
            )

        current_round = session.rounds.filter(status=TuneTriviaRound.Status.PLAYING).first()
        if not current_round:
            return Response(
                {'detail': 'No active round to reveal.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            current_round.status = TuneTriviaRound.Status.REVEALED
            current_round.revealed_at = timezone.now()
            current_round.save()

            # Score all guesses for this round
            self._score_round(current_round)

        output = TuneTriviaRoundRevealedSerializer(current_round)
        return Response(output.data)

    @action(detail=True, methods=['post'], url_path='next-round')
    def next_round(self, request, id=None):
        """Advance to the next round (host only)."""
        session = self.get_object()

        if session.host != request.user:
            return Response(
                {'detail': 'Only the host can advance rounds.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Mark current round as finished
        current_round = session.rounds.filter(
            status__in=[TuneTriviaRound.Status.PLAYING, TuneTriviaRound.Status.REVEALED]
        ).first()

        if current_round:
            current_round.status = TuneTriviaRound.Status.FINISHED
            current_round.save()

        # Find the next pending round
        next_round = session.rounds.filter(status=TuneTriviaRound.Status.PENDING).first()

        if not next_round:
            # No more rounds - end the game
            session.status = TuneTriviaSession.Status.FINISHED
            session.finished_at = timezone.now()
            session.save()

            if session.mode == TuneTriviaSession.Mode.PARTY:
                self._update_leaderboard(session)

            # Return empty round data with special status to signal game end
            return Response(
                {
                    'id': 0,
                    'round_number': 0,
                    'status': 'finished',
                    'track_name': '',
                    'artist_name': '',
                    'album_name': '',
                    'album_art_url': '',
                    'preview_url': '',
                    'trivia': None,
                    'started_at': None,
                    'revealed_at': None,
                    'game_finished': True
                },
                status=status.HTTP_200_OK
            )

        # Start the next round
        next_round.status = TuneTriviaRound.Status.PLAYING
        next_round.started_at = timezone.now()
        next_round.save()

        output = TuneTriviaRoundSerializer(next_round)
        return Response(output.data)

    @action(detail=True, methods=['get'], url_path='state')
    def state(self, request, id=None):
        """Get the current session state for polling."""
        session = self.get_object()
        output = TuneTriviaSessionDetailSerializer(session, context={'request': request})
        return Response(output.data)

    # ==================== Track Management ====================

    @action(detail=True, methods=['post'], url_path='tracks')
    def add_track(self, request, id=None):
        """Add a track to the session."""
        session = self.get_object()

        if session.status != TuneTriviaSession.Status.LOBBY:
            return Response(
                {'detail': 'Can only add tracks in lobby.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if session.rounds.count() >= session.max_songs:
            return Response(
                {'detail': f'Maximum of {session.max_songs} songs reached.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = AddTrackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        track_id = serializer.validated_data['track_id']

        # Check for duplicate
        if session.rounds.filter(spotify_track_id=track_id).exists():
            return Response(
                {'detail': 'This track is already in the session.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch track info from Spotify
        track_service = TrackSelectionService()
        track_info = track_service.get_track_by_id(track_id)

        if not track_info:
            return Response(
                {'detail': 'Track not found or has no preview available.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Generate trivia if enabled
        trivia = None
        if session.enable_trivia:
            trivia_service = TriviaGenerationService()
            trivia = trivia_service.generate_trivia(track_info)

        round_number = session.rounds.count() + 1
        round_obj = TuneTriviaRound.objects.create(
            session=session,
            round_number=round_number,
            spotify_track_id=track_info['spotify_id'],
            track_name=track_info['track_name'],
            artist_name=track_info['artist_name'],
            album_name=track_info.get('album_name', ''),
            album_art_url=track_info.get('album_art_url', ''),
            preview_url=track_info.get('preview_url', ''),
            trivia=trivia,
        )

        output = TuneTriviaRoundSerializer(round_obj)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='auto-select')
    def auto_select_tracks(self, request, id=None):
        """Auto-select tracks based on session filters."""
        session = self.get_object()

        if session.status != TuneTriviaSession.Status.LOBBY:
            return Response(
                {'detail': 'Can only add tracks in lobby.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        count = int(request.query_params.get('count', session.max_songs - session.rounds.count()))
        count = min(count, session.max_songs - session.rounds.count())

        if count <= 0:
            return Response(
                {'detail': 'No slots available for new tracks.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get existing track IDs to avoid duplicates
        existing_ids = set(session.rounds.values_list('spotify_track_id', flat=True))

        # Fetch random tracks from Spotify
        track_service = TrackSelectionService()
        tracks = track_service.get_random_tracks(
            count=count + 10,  # Fetch extra to account for duplicates
            decade=session.auto_select_decade,
            genre=session.auto_select_genre,
            artist=session.auto_select_artist,
        )

        # Filter out duplicates and create rounds
        trivia_service = TriviaGenerationService()
        created_rounds = []

        for track_info in tracks:
            if len(created_rounds) >= count:
                break

            if track_info['spotify_id'] in existing_ids:
                continue

            # Generate trivia if enabled
            trivia = None
            if session.enable_trivia:
                trivia = trivia_service.generate_trivia(track_info)

            round_number = session.rounds.count() + 1
            round_obj = TuneTriviaRound.objects.create(
                session=session,
                round_number=round_number,
                spotify_track_id=track_info['spotify_id'],
                track_name=track_info['track_name'],
                artist_name=track_info['artist_name'],
                album_name=track_info.get('album_name', ''),
                album_art_url=track_info.get('album_art_url', ''),
                preview_url=track_info.get('preview_url', ''),
                trivia=trivia,
            )
            created_rounds.append(round_obj)
            existing_ids.add(track_info['spotify_id'])

        output = TuneTriviaRoundSerializer(created_rounds, many=True)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='search-tracks')
    def search_tracks(self, request):
        """Search for tracks by query string."""
        query = request.query_params.get('q', '')
        if not query or len(query) < 2:
            return Response(
                {'detail': 'Search query must be at least 2 characters.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        limit = int(request.query_params.get('limit', 20))
        limit = min(limit, 50)  # Cap at 50

        track_service = TrackSelectionService()
        tracks = track_service.search_tracks(query, limit=limit)

        # Format response for iOS app
        results = [
            {
                'id': t['spotify_id'],
                'name': t['track_name'],
                'artist_name': t['artist_name'],
                'album_name': t['album_name'],
                'album_art_url': t['album_art_url'],
                'preview_url': t['preview_url'],
            }
            for t in tracks
        ]

        return Response(results)

    # ==================== Player Management (Host Mode) ====================

    @action(detail=True, methods=['post'], url_path='players')
    def add_player(self, request, id=None):
        """Add a manual player (Host Mode only)."""
        session = self.get_object()

        if session.host != request.user:
            return Response(
                {'detail': 'Only the host can add players.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if session.mode != TuneTriviaSession.Mode.HOST:
            return Response(
                {'detail': 'Manual players can only be added in Host Mode.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = AddPlayerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        display_name = serializer.validated_data['display_name']

        # Check for duplicate name
        if session.players.filter(display_name=display_name).exists():
            return Response(
                {'detail': 'A player with this name already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        player = TuneTriviaPlayer.objects.create(
            session=session,
            display_name=display_name,
            user=None  # Manual player has no user account
        )

        output = TuneTriviaPlayerSerializer(player)
        return Response(output.data, status=status.HTTP_201_CREATED)

    # ==================== Helper Methods ====================

    def _score_round(self, round_obj):
        """Score all guesses for a round."""
        for guess in round_obj.guesses.all():
            points = 0

            # Check song guess
            if fuzzy_match(guess.song_guess, round_obj.track_name):
                guess.song_correct = True
                points += 100

            # Check artist guess
            if fuzzy_match(guess.artist_guess, round_obj.artist_name):
                guess.artist_correct = True
                points += 50

            guess.points_earned = points
            guess.save()

            # Update player's total score
            guess.player.total_score += points
            guess.player.save()

    def _update_leaderboard(self, session):
        """Update global leaderboard after a game ends."""
        for player in session.players.filter(user__isnull=False):
            entry, created = TuneTriviaLeaderboardEntry.objects.get_or_create(
                user=player.user,
                defaults={'display_name': player.display_name}
            )

            entry.total_score += player.total_score
            entry.total_games += 1

            # Count correct guesses
            correct_songs = player.guesses.filter(song_correct=True).count()
            correct_artists = player.guesses.filter(artist_correct=True).count()
            entry.total_correct_songs += correct_songs
            entry.total_correct_artists += correct_artists

            entry.save()


class TuneTriviaPlayerViewSet(viewsets.ModelViewSet):
    """ViewSet for managing players."""
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TuneTriviaPlayerSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return TuneTriviaPlayer.objects.filter(
            Q(session__host=self.request.user) | Q(user=self.request.user)
        )

    @action(detail=True, methods=['post'], url_path='award')
    def award_points(self, request, id=None):
        """Award points to a player (Host Mode only)."""
        player = self.get_object()
        session = player.session

        if session.host != request.user:
            return Response(
                {'detail': 'Only the host can award points.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if session.mode != TuneTriviaSession.Mode.HOST:
            return Response(
                {'detail': 'Manual point awarding is only for Host Mode.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = AwardPointsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        points = serializer.validated_data['points']

        player.total_score += points
        player.save()

        output = TuneTriviaPlayerSerializer(player)
        return Response(output.data)


class TuneTriviaRoundViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for rounds."""
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TuneTriviaRoundSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return TuneTriviaRound.objects.filter(
            Q(session__host=self.request.user) | Q(session__players__user=self.request.user)
        ).distinct()

    @action(detail=True, methods=['post'], url_path='guess')
    def submit_guess(self, request, id=None):
        """Submit a guess for a round."""
        round_obj = self.get_object()
        session = round_obj.session

        if round_obj.status != TuneTriviaRound.Status.PLAYING:
            return Response(
                {'detail': 'Can only submit guesses for active rounds.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the player
        try:
            player = session.players.get(user=request.user)
        except TuneTriviaPlayer.DoesNotExist:
            return Response(
                {'detail': 'You are not a player in this session.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if already submitted
        if round_obj.guesses.filter(player=player).exists():
            return Response(
                {'detail': 'You have already submitted a guess for this round.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = SubmitGuessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        guess = TuneTriviaGuess.objects.create(
            round=round_obj,
            player=player,
            song_guess=serializer.validated_data.get('song_guess'),
            artist_guess=serializer.validated_data.get('artist_guess'),
        )

        output = TuneTriviaGuessSerializer(guess)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='guesses')
    def get_guesses(self, request, id=None):
        """Get all guesses for a round (after reveal)."""
        round_obj = self.get_object()

        if round_obj.status not in [TuneTriviaRound.Status.REVEALED, TuneTriviaRound.Status.FINISHED]:
            return Response(
                {'detail': 'Guesses are only visible after reveal.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        guesses = round_obj.guesses.all()
        output = TuneTriviaGuessSerializer(guesses, many=True)
        return Response(output.data)


class TuneTriviaLeaderboardViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for the global leaderboard."""
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.AllowAny]
    serializer_class = LeaderboardEntrySerializer
    queryset = TuneTriviaLeaderboardEntry.objects.all()

    def list(self, request):
        """Get the leaderboard."""
        limit = int(request.query_params.get('limit', 50))
        entries = self.queryset[:limit]
        serializer = self.get_serializer(entries, many=True)
        return Response(serializer.data)
