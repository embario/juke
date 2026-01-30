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
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    city_lat = models.FloatField(
        null=True, blank=True, db_index=True,
        help_text='Latitude rounded to 2 decimal places (~1.1km / city-centroid precision)',
    )
    city_lng = models.FloatField(
        null=True, blank=True, db_index=True,
        help_text='Longitude rounded to 2 decimal places (~1.1km / city-centroid precision)',
    )
    custom_data = models.JSONField(blank=True, default=dict)
    clout = models.FloatField(
        default=0.0,
        help_text='Streaming clout metric, 0.0-1.0',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.city_lat is not None:
            self.city_lat = round(self.city_lat, 2)
        if self.city_lng is not None:
            self.city_lng = round(self.city_lng, 2)
        self.clout = max(0.0, min(1.0, self.clout))
        super().save(*args, **kwargs)
