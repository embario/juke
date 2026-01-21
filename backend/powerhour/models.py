import uuid
import string
import random

from django.conf import settings
from django.db import models


def generate_invite_code():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=8))


class PowerHourSession(models.Model):
    STATUS_CHOICES = [
        ('lobby', 'Lobby'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('ended', 'Ended'),
    ]

    TRANSITION_CHOICES = [
        ('airhorn', 'Air Horn'),
        ('buzzer', 'Buzzer'),
        ('bell', 'Bell'),
        ('whistle', 'Whistle'),
        ('glass_clink', 'Glass Clink'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hosted_sessions',
    )
    title = models.CharField(max_length=200)
    invite_code = models.CharField(max_length=8, unique=True, default=generate_invite_code)

    # Configuration
    tracks_per_player = models.PositiveIntegerField(default=3)
    max_tracks = models.PositiveIntegerField(default=30)
    seconds_per_track = models.PositiveIntegerField(default=60)
    transition_clip = models.CharField(max_length=50, choices=TRANSITION_CHOICES, default='airhorn')
    hide_track_owners = models.BooleanField(default=False)

    # State
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='lobby')
    current_track_index = models.IntegerField(default=-1)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.invite_code})"


class SessionPlayer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        PowerHourSession,
        on_delete=models.CASCADE,
        related_name='players',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='session_memberships',
    )
    is_admin = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'user')
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user.username} in {self.session.title}"


class SessionTrack(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        PowerHourSession,
        on_delete=models.CASCADE,
        related_name='tracks',
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='session_tracks_added',
    )
    track = models.ForeignKey(
        'catalog.Track',
        on_delete=models.CASCADE,
    )
    order = models.PositiveIntegerField()
    start_offset_ms = models.PositiveIntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'track')
        ordering = ['order']

    def __str__(self):
        return f"{self.track.name} (#{self.order}) in {self.session.title}"
