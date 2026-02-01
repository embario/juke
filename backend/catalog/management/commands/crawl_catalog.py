from django.core.management.base import BaseCommand

from catalog.services.catalog_crawl import crawl_catalog


class Command(BaseCommand):
    help = 'Crawl Spotify by genre seed and populate Artists, Albums, and Tracks.'

    def handle(self, *args, **options):
        result = crawl_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                f"Catalog crawl finished ("
                f"artists={result.artists_created}, "
                f"albums={result.albums_created}, "
                f"tracks={result.tracks_created}, "
                f"failed={len(result.failed_artist_ids)})."
            )
        )
        if result.failed_artist_ids:
            self.stdout.write(
                self.style.WARNING(
                    f"Failed artist IDs: {result.failed_artist_ids}"
                )
            )
