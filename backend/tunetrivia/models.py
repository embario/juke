import random
import string

from django.conf import settings
from django.db import models


def generate_session_code():
    """Generate a 6-character alphanumeric code for session joining."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


class TuneTriviaSession(models.Model):
    """A TuneTrivia game session."""

    class Mode(models.TextChoices):
        HOST = 'host', 'Host Mode'
        PARTY = 'party', 'Party Mode'

    class Status(models.TextChoices):
        LOBBY = 'lobby', 'Lobby'
        PLAYING = 'playing', 'Playing'
        PAUSED = 'paused', 'Paused'
        FINISHED = 'finished', 'Finished'

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=6, unique=True, default=generate_session_code)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hosted_tunetrivia_sessions'
    )
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.PARTY)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.LOBBY)

    # Configuration
    max_songs = models.PositiveIntegerField(default=10)
    seconds_per_song = models.PositiveIntegerField(default=30)
    enable_trivia = models.BooleanField(default=True)

    # Auto-select filters
    auto_select_decade = models.CharField(max_length=20, blank=True, null=True)
    auto_select_genre = models.CharField(max_length=100, blank=True, null=True)
    auto_select_artist = models.CharField(max_length=200, blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def current_round(self):
        """Get the current active round."""
        return self.rounds.filter(
            status__in=[TuneTriviaRound.Status.PLAYING, TuneTriviaRound.Status.REVEALED]
        ).order_by('-round_number').first()


class TuneTriviaPlayer(models.Model):
    """A player in a TuneTrivia session."""

    session = models.ForeignKey(
        TuneTriviaSession,
        on_delete=models.CASCADE,
        related_name='players'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tunetrivia_participations',
        blank=True,
        null=True
    )
    # For host mode - players without accounts
    display_name = models.CharField(max_length=100)
    is_host = models.BooleanField(default=False)

    # Scoring
    total_score = models.IntegerField(default=0)

    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('session', 'user'), ('session', 'display_name')]
        ordering = ['-total_score', 'joined_at']

    def __str__(self):
        return f"{self.display_name} in {self.session.name}"


class TuneTriviaRound(models.Model):
    """A round (song) in a TuneTrivia session."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PLAYING = 'playing', 'Playing'
        REVEALED = 'revealed', 'Revealed'
        FINISHED = 'finished', 'Finished'

    session = models.ForeignKey(
        TuneTriviaSession,
        on_delete=models.CASCADE,
        related_name='rounds'
    )
    round_number = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    # Track info (from Spotify)
    spotify_track_id = models.CharField(max_length=100)
    track_name = models.CharField(max_length=300)
    artist_name = models.CharField(max_length=300)
    album_name = models.CharField(max_length=300, blank=True)
    album_art_url = models.URLField(blank=True)
    preview_url = models.URLField(blank=True, null=True)

    # Trivia
    trivia = models.TextField(blank=True, null=True)

    # Timestamps
    started_at = models.DateTimeField(blank=True, null=True)
    revealed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = [('session', 'round_number'), ('session', 'spotify_track_id')]
        ordering = ['round_number']

    def __str__(self):
        return f"Round {self.round_number}: {self.track_name}"


class TuneTriviaGuess(models.Model):
    """A player's guess for a round."""

    round = models.ForeignKey(
        TuneTriviaRound,
        on_delete=models.CASCADE,
        related_name='guesses'
    )
    player = models.ForeignKey(
        TuneTriviaPlayer,
        on_delete=models.CASCADE,
        related_name='guesses'
    )

    # Guesses
    song_guess = models.CharField(max_length=300, blank=True, null=True)
    artist_guess = models.CharField(max_length=300, blank=True, null=True)
    trivia_guess = models.CharField(max_length=300, blank=True, null=True)

    # Scoring
    song_correct = models.BooleanField(default=False)
    artist_correct = models.BooleanField(default=False)
    trivia_correct = models.BooleanField(default=False)
    points_earned = models.IntegerField(default=0)

    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('round', 'player')]

    def __str__(self):
        return f"{self.player.display_name}'s guess for Round {self.round.round_number}"


class TuneTriviaLeaderboardEntry(models.Model):
    """Aggregated leaderboard entry for a user across all Party Mode games."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tunetrivia_leaderboard'
    )
    display_name = models.CharField(max_length=100)
    total_score = models.IntegerField(default=0)
    total_games = models.IntegerField(default=0)
    total_correct_songs = models.IntegerField(default=0)
    total_correct_artists = models.IntegerField(default=0)
    total_correct_trivia = models.IntegerField(default=0)

    # Timestamps
    last_played_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-total_score']

    def __str__(self):
        return f"{self.display_name}: {self.total_score} pts"
