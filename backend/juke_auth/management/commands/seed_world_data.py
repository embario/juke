import random
from django.core.management.base import BaseCommand
from juke_auth.models import JukeUser, MusicProfile

# Major city centroids with population weights for realistic clustering
CITY_CENTERS = [
    (40.71, -74.01, 8, 'New York', 'USA'),
    (34.05, -118.24, 7, 'Los Angeles', 'USA'),
    (51.51, -0.13, 7, 'London', 'UK'),
    (48.86, 2.35, 5, 'Paris', 'France'),
    (35.68, 139.69, 6, 'Tokyo', 'Japan'),
    (-23.55, -46.63, 5, 'São Paulo', 'Brazil'),
    (19.43, -99.13, 4, 'Mexico City', 'Mexico'),
    (55.76, 37.62, 4, 'Moscow', 'Russia'),
    (28.61, 77.23, 5, 'Delhi', 'India'),
    (39.91, 116.40, 5, 'Beijing', 'China'),
    (-33.87, 151.21, 4, 'Sydney', 'Australia'),
    (37.57, 126.98, 4, 'Seoul', 'South Korea'),
    (52.52, 13.41, 4, 'Berlin', 'Germany'),
    (41.90, 12.50, 3, 'Rome', 'Italy'),
    (43.65, -79.38, 4, 'Toronto', 'Canada'),
    (41.88, -87.63, 5, 'Chicago', 'USA'),
    (30.04, 31.24, 3, 'Cairo', 'Egypt'),
    (-34.60, -58.38, 3, 'Buenos Aires', 'Argentina'),
    (1.35, 103.82, 3, 'Singapore', 'Singapore'),
    (13.76, 100.50, 3, 'Bangkok', 'Thailand'),
    (25.20, 55.27, 3, 'Dubai', 'UAE'),
    (59.33, 18.07, 3, 'Stockholm', 'Sweden'),
    (45.46, 9.19, 3, 'Milan', 'Italy'),
    (29.76, -95.37, 4, 'Houston', 'USA'),
    (33.75, -84.39, 4, 'Atlanta', 'USA'),
    (6.52, 3.38, 3, 'Lagos', 'Nigeria'),
    (-1.29, 36.82, 2, 'Nairobi', 'Kenya'),
    (35.69, 51.39, 2, 'Tehran', 'Iran'),
    (14.60, 120.98, 3, 'Manila', 'Philippines'),
    (22.32, 114.17, 3, 'Hong Kong', 'China'),
]

SUPER_GENRES = ['pop', 'rock', 'country', 'rap', 'folk', 'jazz', 'classical']

SAMPLE_ARTISTS = {
    'pop': ['Taylor Swift', 'Dua Lipa', 'The Weeknd', 'Billie Eilish', 'Harry Styles'],
    'rock': ['Foo Fighters', 'Arctic Monkeys', 'The Killers', 'Green Day', 'Radiohead'],
    'country': ['Morgan Wallen', 'Luke Combs', 'Chris Stapleton', 'Zach Bryan', 'Kacey Musgraves'],
    'rap': ['Kendrick Lamar', 'Drake', 'J. Cole', 'Tyler the Creator', 'Travis Scott'],
    'folk': ['Bon Iver', 'Fleet Foxes', 'Iron & Wine', 'Phoebe Bridgers', 'Sufjan Stevens'],
    'jazz': ['Kamasi Washington', 'Robert Glasper', 'Esperanza Spalding', 'Norah Jones', 'Chet Baker'],
    'classical': ['Yo-Yo Ma', 'Lang Lang', 'Hilary Hahn', 'Max Richter', 'Ludovico Einaudi'],
}

ADJECTIVES = ['melody', 'bass', 'vinyl', 'synth', 'acoustic', 'drum', 'beat', 'sonic', 'wave', 'groove']
NOUNS = ['maven', 'head', 'child', 'rider', 'soul', 'king', 'queen', 'lover', 'fire', 'dream']


class Command(BaseCommand):
    help = 'Seed 50K synthetic users with globe data for Juke World development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count', type=int, default=50000,
            help='Number of synthetic users to create (default: 50000)',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete all existing seeded users before creating new ones',
        )

    def handle(self, *args, **options):
        count = options['count']
        clear = options['clear']

        if clear:
            seeded_users = JukeUser.objects.filter(username__startswith='jw_')
            profile_count, _ = MusicProfile.objects.filter(user__in=seeded_users).delete()
            deleted_count, _ = seeded_users.delete()
            self.stdout.write(
                f'Cleared {deleted_count} seeded users and {profile_count} profiles.'
            )

        self.stdout.write(f'Seeding {count} synthetic users for Juke World...')

        total_weight = sum(c[2] for c in CITY_CENTERS)
        batch_size = 1000
        users_created = 0

        for batch_start in range(0, count, batch_size):
            batch_end = min(batch_start + batch_size, count)
            users = []
            profiles = []

            for i in range(batch_start, batch_end):
                # Pick a city weighted by population
                r = random.random() * total_weight
                city = CITY_CENTERS[0]
                for c in CITY_CENTERS:
                    r -= c[2]
                    if r <= 0:
                        city = c
                        break

                # Scatter around city center
                spread = 2.0 + random.random() * 3.0
                lat = round(city[0] + (random.random() - 0.5) * spread, 2)
                lng = round(city[1] + (random.random() - 0.5) * spread, 2)

                # Power-law clout distribution
                clout = round(0.1 + random.random() * 0.7, 2)

                # Genre assignment (weighted toward pop/rock/rap)
                genre_weights = [3, 2.5, 1, 2, 1, 1, 0.5]
                genre = random.choices(SUPER_GENRES, weights=genre_weights, k=1)[0]

                # Generate username
                adj = random.choice(ADJECTIVES)
                noun = random.choice(NOUNS)
                username = f'jw_{adj}{noun}{i}'

                user = JukeUser(
                    username=username,
                    email=f'{username}@juke-seed.local',
                )
                user.set_unusable_password()
                users.append(user)

                # Pick favorite data
                top_artists = random.sample(SAMPLE_ARTISTS[genre], min(3, len(SAMPLE_ARTISTS[genre])))
                genres_list = [genre] + random.sample(
                    [g for g in SUPER_GENRES if g != genre],
                    min(2, len(SUPER_GENRES) - 1),
                )

                city_name = city[3]
                country_name = city[4]
                profiles.append({
                    'display_name': f'{adj.capitalize()} {noun.capitalize()}',
                    'tagline': f'{genre.capitalize()} enthusiast from {city_name}',
                    'location': f'{city_name}, {country_name}',
                    'city_lat': lat,
                    'city_lng': lng,
                    'clout': clout,
                    'favorite_genres': genres_list,
                    'favorite_artists': top_artists,
                })

            # Bulk create users
            JukeUser.objects.bulk_create(users, ignore_conflicts=True)

            # Fetch back the users to get IDs (bulk_create with ignore_conflicts
            # may not return IDs on all backends)
            usernames = [u.username for u in users]
            user_map = {
                u.username: u
                for u in JukeUser.objects.filter(username__in=usernames)
            }

            # Create profiles
            profile_objects = []
            for j, profile_data in enumerate(profiles):
                username = users[j].username
                if username in user_map:
                    profile_objects.append(MusicProfile(
                        user=user_map[username],
                        **profile_data,
                    ))

            MusicProfile.objects.bulk_create(profile_objects, ignore_conflicts=True)
            users_created += len(profile_objects)

            if (batch_start + batch_size) % 5000 == 0 or batch_end == count:
                self.stdout.write(f'  ...created {users_created}/{count} users')

        self.stdout.write(self.style.SUCCESS(
            f'Successfully seeded {users_created} users with globe data.'
        ))
