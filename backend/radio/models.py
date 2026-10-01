"""Radio stations, exclusions and listening signals for the Juke app."""
import uuid

from django.conf import settings
from django.db import models


STATION_KIND_PERSONAL = 'personal'
STATION_KIND_CUSTOM = 'custom'
STATION_KIND_CHOICES = (
    (STATION_KIND_PERSONAL, 'Personal'),
    (STATION_KIND_CUSTOM, 'Custom'),
)

EXCLUSION_SCOPE_STATION = 'station'
EXCLUSION_SCOPE_EVERYWHERE = 'everywhere'
EXCLUSION_SCOPE_CHOICES = (
    (EXCLUSION_SCOPE_STATION, 'This station'),
    (EXCLUSION_SCOPE_EVERYWHERE, 'Everywhere'),
)
EXCLUSION_KIND_CHOICES = (
    ('track', 'Track'),
    ('artist', 'Artist'),
    ('genre', 'Genre'),
    ('text', 'Text'),
)

LISTENING_EVENTS = ('play', 'complete', 'skip', 'less', 'not_on_station', 'never_artist', 'seek', 'save', 'recognized')
# Internal-only event recorded when the radio queues a track; never accepted from clients.
QUEUED_EVENT = 'queued'
LISTENING_EVENT_CHOICES = tuple((value, value) for value in LISTENING_EVENTS + (QUEUED_EVENT,))


class Station(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='radio_stations')
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=STATION_KIND_CHOICES, default=STATION_KIND_CUSTOM)
    frequency = models.DecimalField(max_digits=4, decimal_places=1)
    seeds = models.JSONField(default=list, blank=True)
    feelings = models.JSONField(default=list, blank=True)
    learning = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['frequency', 'created_at']
        indexes = [models.Index(fields=['user', 'kind'], name='radio_station_user_kind_idx')]
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(kind=STATION_KIND_PERSONAL),
                name='radio_station_one_personal_per_user',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.frequency})'

    @property
    def is_personal(self):
        return self.kind == STATION_KIND_PERSONAL


class Exclusion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='radio_exclusions')
    # NULL station means the exclusion applies everywhere.
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.CASCADE, related_name='exclusions')
    scope = models.CharField(max_length=16, choices=EXCLUSION_SCOPE_CHOICES)
    kind = models.CharField(max_length=16, choices=EXCLUSION_KIND_CHOICES)
    value = models.CharField(max_length=200)
    label = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['user', 'station'], name='radio_exclusion_user_stn_idx')]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'scope', 'kind', 'value'],
                condition=models.Q(station__isnull=True),
                name='radio_exclusion_everywhere_uniq',
            ),
            models.UniqueConstraint(
                fields=['user', 'station', 'kind', 'value'],
                condition=models.Q(station__isnull=False),
                name='radio_exclusion_station_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.scope}:{self.kind}:{self.value}'


class TrackReaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='radio_reactions')
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL, related_name='reactions')
    spotify_track_id = models.CharField(max_length=64)
    reactions = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'spotify_track_id'], name='radio_reaction_user_track_uniq'),
        ]
        indexes = [models.Index(fields=['user', '-updated_at'], name='radio_reaction_user_recent_idx')]

    def __str__(self):
        return f'{self.spotify_track_id}: {" ".join(self.reactions)}'


class ListeningEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='radio_events')
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL, related_name='events')
    spotify_track_id = models.CharField(max_length=64)
    spotify_artist_id = models.CharField(max_length=64, blank=True, default='')
    event = models.CharField(max_length=24, choices=LISTENING_EVENT_CHOICES)
    position_ms = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(max_length=32, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='radio_event_user_recent_idx'),
            models.Index(fields=['user', 'event', '-created_at'], name='radio_event_user_kind_idx'),
        ]

    def __str__(self):
        return f'{self.event}:{self.spotify_track_id}'
