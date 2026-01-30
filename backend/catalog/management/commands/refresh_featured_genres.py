from django.core.management.base import BaseCommand

from catalog.services.featured_genres import refresh_featured_genres


class Command(BaseCommand):
    help = 'Refresh featured genres cache and top artist image URLs from Spotify.'

    def handle(self, *args, **options):
        payload = refresh_featured_genres(enforce_budget=False)
        self.stdout.write(
            self.style.SUCCESS(f"Featured genres refreshed ({len(payload)} genres).")
        )
