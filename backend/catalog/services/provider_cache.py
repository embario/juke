"""Provider-neutral identity and freshness metadata for read-through catalog data."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Album,
    AlbumExternalIdentifier,
    Artist,
    ArtistExternalIdentifier,
    Genre,
    GenreExternalIdentifier,
    Track,
    TrackExternalIdentifier,
)


RESOURCE_CONFIG = {
    'artist': (Artist, ArtistExternalIdentifier, 'artist'),
    'album': (Album, AlbumExternalIdentifier, 'album'),
    'track': (Track, TrackExternalIdentifier, 'track'),
    'genre': (Genre, GenreExternalIdentifier, 'genre'),
}


def record_provider_identity(
    resource,
    *,
    resource_type: str,
    provider: str,
    external_id: str,
    provider_data: dict | None = None,
    provider_url: str = '',
    market: str = '',
    ttl_seconds: int | None = None,
):
    """Attach/update one provider identity without conflating provider namespaces."""
    _, identifier_model, relation_name = RESOURCE_CONFIG[resource_type]
    refreshed_at = timezone.now()
    expires_at = refreshed_at + timedelta(seconds=ttl_seconds) if ttl_seconds else None
    relation_value = resource.juke_id
    with transaction.atomic():
        identifier = (
            identifier_model.objects
            .select_for_update()
            .filter(source=provider, external_id=external_id)
            .first()
        )
        if identifier and getattr(identifier, f'{relation_name}_id') != relation_value:
            raise ValidationError(
                f"{provider}:{external_id} is already assigned to another {resource_type}."
            )
        values = {
            'provider_data': provider_data or {},
            'provider_url': provider_url,
            'market': market,
            'last_refreshed_at': refreshed_at,
            'cache_expires_at': expires_at,
        }
        if identifier:
            for field_name, value in values.items():
                setattr(identifier, field_name, value)
            identifier.save(update_fields=[*values.keys()])
        else:
            identifier = identifier_model.objects.create(
                **{
                    f'{relation_name}_id': relation_value,
                    'source': provider,
                    'external_id': external_id,
                    **values,
                },
            )
    return identifier


def upsert_provider_resource(
    *,
    resource_type: str,
    provider: str,
    external_id: str,
    defaults: dict,
    provider_data: dict | None = None,
    provider_url: str = '',
    market: str = '',
    ttl_seconds: int | None = None,
):
    """Create/update a resource from a provider-normalized record.

    This is the persistence contract for future adapters. It deliberately does
    not infer that matching names across providers are the same canonical entity.
    Cross-provider merging belongs to the identity-resolution layer.
    """
    model, identifier_model, relation_name = RESOURCE_CONFIG[resource_type]
    with transaction.atomic():
        identifier = (
            identifier_model.objects
            .select_related(relation_name)
            .filter(source=provider, external_id=external_id)
            .first()
        )
        if identifier:
            resource = getattr(identifier, relation_name)
            for field_name, value in defaults.items():
                setattr(resource, field_name, value)
            resource.save()
        else:
            resource = None
            if provider == 'spotify':
                resource = model.objects.filter(spotify_id=external_id).first()
            if resource is None:
                resource = model.objects.create(
                    spotify_id=external_id if provider == 'spotify' else None,
                    **defaults,
                )

        if provider == 'spotify':
            resource.spotify_id = external_id
            resource.spotify_data = provider_data or {}
            resource.save(update_fields=['spotify_id', 'spotify_data', 'modified_at'])

        identity = record_provider_identity(
            resource,
            resource_type=resource_type,
            provider=provider,
            external_id=external_id,
            provider_data=provider_data,
            provider_url=provider_url,
            market=market,
            ttl_seconds=ttl_seconds,
        )
    return resource, identity
