from django.db import models
from django.contrib.auth.models import AbstractUser


class JukeUser(AbstractUser):
    email = models.EmailField(unique=True, null=False, blank=False)


class MusicProfile(models.Model):
    name = models.CharField(blank=True, null=True, max_length=200)
    user = models.OneToOneField(
        JukeUser,
        on_delete=models.PROTECT,
        related_name='music_profile',
    )
    display_name = models.CharField(blank=True, default='', max_length=200)
    tagline = models.CharField(blank=True, default='', max_length=280)
    bio = models.TextField(blank=True, default='')
    location = models.CharField(blank=True, default='', max_length=120)
    avatar_url = models.URLField(blank=True, default='')
    favorite_genres = models.JSONField(blank=True, default=list)
    favorite_artists = models.JSONField(blank=True, default=list)
    favorite_albums = models.JSONField(blank=True, default=list)
    favorite_tracks = models.JSONField(blank=True, default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
