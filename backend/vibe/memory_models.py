"""Private, profile-owned music memories and reusable personal vocabulary."""
import uuid

from django.conf import settings
from django.db import models


class MusicMemory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey('juke_auth.MusicProfile', on_delete=models.CASCADE, related_name='music_memories')
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    place = models.CharField(max_length=200, blank=True)
    people = models.JSONField(default=list)
    songs = models.JSONField(default=list)
    tags = models.JSONField(default=list)
    generated_tags = models.JSONField(default=list)
    excluded_tags = models.JSONField(default=list)
    classification = models.JSONField(default=dict)
    recommendation_signals = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-occurred_at', '-created_at')
        indexes = [models.Index(fields=('profile', '-occurred_at'), name='vibe_mem_profile_date_idx')]


class MemoryTag(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memory_tags')
    label = models.CharField(max_length=60)
    normalized = models.CharField(max_length=180)

    class Meta:
        ordering = ('normalized',)
        constraints = [models.UniqueConstraint(fields=('user', 'normalized'), name='vibe_tag_user_normalized_unique')]


class MemoryMedia(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memory_media')
    memory = models.ForeignKey(MusicMemory, null=True, blank=True, on_delete=models.CASCADE, related_name='media')
    kind = models.CharField(max_length=8)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=64)
    # Private bytes never pass through a publicly served MEDIA_URL/static directory.
    content = models.BinaryField()
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
