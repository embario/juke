from django.core.management.base import BaseCommand

from catalog.services.genre_sync import sync_spotify_genres


class Command(BaseCommand):
    help = 'Synchronize Spotify genre seeds into the local database.'

    def handle(self, *args, **options):
        result = sync_spotify_genres()
        self.stdout.write(
            self.style.SUCCESS(
                f"Spotify genres synchronized (created={result.created}, updated={result.updated}, total={result.total})."
            )
        )
