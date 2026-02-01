from django.core.management.base import BaseCommand

from recommender.services.audio_ingest import ingest_training_data


class Command(BaseCommand):
    help = 'Ingest audio features from Spotify for every track in the catalog.'

    def handle(self, *args, **options):
        result = ingest_training_data()
        self.stdout.write(
            self.style.SUCCESS(
                f"Audio-feature ingest finished ("
                f"ingested={result.ingested}, "
                f"skipped={result.skipped}, "
                f"failed={result.failed})."
            )
        )
        if result.failed_track_ids:
            self.stdout.write(
                self.style.WARNING(
                    f"Failed track IDs: {result.failed_track_ids}"
                )
            )
