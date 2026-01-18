from __future__ import annotations

from django.db import models

from catalog.models import Artist, Album, Track


class EmbeddingBase(models.Model):
    vector = models.JSONField(default=list)
    model_version = models.CharField(max_length=32)
    quality_score = models.FloatField(default=0.0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def as_payload(self) -> dict:
        return {
            'vector': self.vector,
            'model_version': self.model_version,
            'quality_score': self.quality_score,
            'metadata': self.metadata,
        }


class ArtistEmbedding(EmbeddingBase):
    artist = models.OneToOneField(Artist, related_name='embedding', on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"Embedding(artist={self.artist.name})"


class AlbumEmbedding(EmbeddingBase):
    album = models.OneToOneField(Album, related_name='embedding', on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"Embedding(album={self.album.name})"


class TrackEmbedding(EmbeddingBase):
    track = models.OneToOneField(Track, related_name='embedding', on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"Embedding(track={self.track.name})"
