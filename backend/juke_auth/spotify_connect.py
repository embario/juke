import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from juke_auth.models import SpotifyConnectTicket


class SpotifyConnectTicketError(Exception):
    pass


@dataclass(frozen=True)
class IssuedSpotifyConnectTicket:
    secret: str
    expires_at: object


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode('ascii')).hexdigest()


def issue_spotify_connect_ticket(*, user, return_to: str) -> IssuedSpotifyConnectTicket:
    secret = secrets.token_urlsafe(48)
    expires_at = timezone.now() + timedelta(
        seconds=settings.SPOTIFY_CONNECT_TICKET_TTL_SECONDS,
    )
    SpotifyConnectTicket.objects.create(
        user=user,
        secret_digest=_digest(secret),
        return_to=return_to,
        expires_at=expires_at,
    )
    return IssuedSpotifyConnectTicket(secret=secret, expires_at=expires_at)


def consume_spotify_connect_ticket(secret: str):
    if not secret or len(secret) > 256:
        raise SpotifyConnectTicketError('Invalid or expired Spotify connection ticket.')
    now = timezone.now()
    with transaction.atomic():
        ticket = (
            SpotifyConnectTicket.objects.select_for_update()
            .select_related('user')
            .filter(secret_digest=_digest(secret))
            .first()
        )
        if ticket is None or ticket.consumed_at is not None or ticket.expires_at <= now:
            raise SpotifyConnectTicketError('Invalid or expired Spotify connection ticket.')
        ticket.consumed_at = now
        ticket.save(update_fields=('consumed_at',))
        return ticket
