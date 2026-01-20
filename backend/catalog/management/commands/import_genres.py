from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from catalog.models import Genre


class Command(BaseCommand):
    help = 'Imports Genres found in genres.txt'

    def handle(self, *args, **options):
        genres_path = settings.BASE_DIR / 'genres.txt'

        try:
            with genres_path.open('r') as genres_f:
                for idx, genre_name in enumerate(genres_f.readlines()):
                    g1 = Genre.objects.create(name=genre_name.strip('\n'), spotify_id=f'fake-spotify-id-{idx}')
                    self.stdout.write(self.style.SUCCESS(f"Genre '{g1.name}' added."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(e))
            raise CommandError('An error occurred. Please fix and try again.')

        self.stdout.write(self.style.SUCCESS('Successfully imported genres'))
