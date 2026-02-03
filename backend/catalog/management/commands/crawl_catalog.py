import json
import logging
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.services.catalog_crawl import crawl_catalog
from catalog import spotify_stub


class Command(BaseCommand):
    help = (
        'Crawl Spotify by genre seed and populate Artists, Albums, and Tracks. '
        '"Updated" means the entity already exists in the DB (artist/album/track) '
        'or the genre seed has already been seen in this run, so creation is skipped.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Run crawl cycles continuously (default: false).',
        )
        parser.add_argument(
            '--loop-sleep',
            type=float,
            default=900,
            help='Seconds to sleep between looped crawl cycles (default: 900).',
        )
        parser.add_argument(
            '--request-delay',
            type=float,
            default=0.2,
            help='Minimum seconds between Spotify API requests (default: 0.2).',
        )
        parser.add_argument(
            '--max-retries',
            type=int,
            default=5,
            help='Max retries for Spotify 429/5xx responses (default: 5).',
        )
        parser.add_argument(
            '--retry-backoff',
            type=float,
            default=1.0,
            help='Base seconds for exponential backoff (default: 1.0).',
        )
        parser.add_argument(
            '--log-file',
            default=None,
            help='Path to append crawl telemetry logs (default: backend/logs/crawl_catalog.log).',
        )
        parser.add_argument(
            '--json-logs',
            action='store_true',
            help='Emit a JSON summary line per crawl cycle (default: false).',
        )
        parser.add_argument(
            '--idle-backoff-multiplier',
            type=float,
            default=2.0,
            help='Multiplier applied to loop sleep when a cycle has no new data (default: 2.0).',
        )
        parser.add_argument(
            '--idle-max-sleep',
            type=float,
            default=3600,
            help='Max seconds to sleep between cycles when idle (default: 3600).',
        )
        parser.add_argument(
            '--memo-ttl',
            type=float,
            default=86400,
            help='Seconds before memoized crawl keys expire in Redis (default: 86400).',
        )
        parser.add_argument(
            '--reset-memo',
            action='store_true',
            help='Clear memoized crawl keys in Redis before starting (default: false).',
        )
        parser.add_argument(
            '--max-artist-retries',
            type=int,
            default=5,
            help='Max retry attempts for partial artists before marking failed (default: 5).',
        )

    def handle(self, *args, **options):
        loop = options['loop']
        loop_sleep = options['loop_sleep']
        request_delay = options['request_delay']
        max_retries = options['max_retries']
        retry_backoff = options['retry_backoff']
        log_file = options['log_file']
        emit_json = options['json_logs']
        idle_backoff = options['idle_backoff_multiplier']
        idle_max_sleep = options['idle_max_sleep']
        memo_ttl = options['memo_ttl']
        reset_memo = options['reset_memo']
        max_artist_retries = options['max_artist_retries']

        log_path = self._configure_file_logging(log_file)
        telemetry_logger = logging.getLogger('catalog.crawl.telemetry')
        telemetry_logger.info('crawl: logging to %s', log_path)
        memo_state = self._configure_memo_backend(
            telemetry_logger,
            memo_ttl_seconds=memo_ttl,
            reset_memo=reset_memo,
        )
        memo_state['max_artist_retries'] = max_artist_retries

        self.stdout.write(
            self.style.WARNING(
                'Updated = already exists in DB (artist/album/track) or genre seed '
                'already processed this run; creation is skipped.'
            )
        )

        use_tui = sys.stdout.isatty()
        tui = None
        if use_tui:
            tui = self._init_tui()
            if tui is None:
                use_tui = False

        cycle = 0
        current_sleep = loop_sleep
        last_missing_summary = None
        while True:
            cycle += 1
            cycle_started = time.monotonic()
            result = crawl_catalog(
                request_delay_seconds=request_delay,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff,
                memo=memo_state,
                progress=tui['progress'] if tui else None,
            )
            cycle_elapsed = time.monotonic() - cycle_started
            missing_summary = self._missing_summary()
            if not tui:
                self.stdout.write(
                    self.style.SUCCESS(
                        "Catalog crawl finished\n"
                        f"  created: artists={result.artists_created} "
                        f"albums={result.albums_created} tracks={result.tracks_created}\n"
                        f"  updated: artists={result.artists_updated} "
                        f"albums={result.albums_updated} tracks={result.tracks_updated}\n"
                        f"  skipped: artists={result.artists_skipped} "
                        f"hydrated_artists={result.artists_fully_hydrated_skipped} "
                        f"albums={result.albums_skipped} tracks={result.tracks_skipped}\n"
                        f"  failed: artists={len(result.failed_artist_ids)} "
                        f"tracks={len(result.failed_track_ids)}\n"
                        f"  missing: artists_not_fully_hydrated={missing_summary['artists_not_fully_hydrated']} "
                        f"albums_not_fully_hydrated={missing_summary['albums_not_fully_hydrated']}\n"
                        f"  completion: {'yes' if result.completed else 'no'} "
                        f"reason={result.completion_reason or 'n/a'}"
                    )
                )
            if result.failed_artist_ids and not tui:
                self.stdout.write(
                    self.style.WARNING(
                        f"Failed artist IDs: {result.failed_artist_ids}"
                    )
                )

            telemetry_logger.info(
                'crawl: cycle=%d elapsed=%.1fs created(artists=%d albums=%d tracks=%d) '
                'updated(artists=%d albums=%d tracks=%d) '
                'skipped(artists=%d hydrated_artists=%d albums=%d tracks=%d) failed(artists=%d tracks=%d) '
                'missing(artists_not_fully_hydrated=%d albums_not_fully_hydrated=%d)',
                cycle,
                cycle_elapsed,
                result.artists_created,
                result.albums_created,
                result.tracks_created,
                result.artists_updated,
                result.albums_updated,
                result.tracks_updated,
                result.artists_skipped,
                result.artists_fully_hydrated_skipped,
                result.albums_skipped,
                result.tracks_skipped,
                len(result.failed_artist_ids),
                len(result.failed_track_ids),
                missing_summary['artists_not_fully_hydrated'],
                missing_summary['albums_not_fully_hydrated'],
            )
            if result.failed_artist_ids:
                telemetry_logger.info(
                    'crawl: failed_artist_ids=%s',
                    result.failed_artist_ids,
                )

            if emit_json:
                telemetry_logger.info(
                    json.dumps(
                        {
                            'event': 'crawl_cycle',
                            'cycle': cycle,
                            'timestamp': timezone.now().isoformat(),
                            'elapsed_seconds': round(cycle_elapsed, 2),
                            'created': {
                                'artists': result.artists_created,
                                'albums': result.albums_created,
                                'tracks': result.tracks_created,
                            },
                            'updated': {
                                'artists': result.artists_updated,
                                'albums': result.albums_updated,
                                'tracks': result.tracks_updated,
                            },
                            'skipped': {
                                'artists': result.artists_skipped,
                                'artists_fully_hydrated': result.artists_fully_hydrated_skipped,
                                'albums': result.albums_skipped,
                                'tracks': result.tracks_skipped,
                            },
                            'failed': {
                                'artists': len(result.failed_artist_ids),
                                'artist_ids': result.failed_artist_ids,
                                'tracks': len(result.failed_track_ids),
                            },
                            'missing': missing_summary,
                            'settings': {
                                'request_delay_seconds': request_delay,
                                'max_retries': max_retries,
                                'retry_backoff_seconds': retry_backoff,
                                'loop_sleep_seconds': loop_sleep if loop else None,
                            },
                            'completed': result.completed,
                            'completion_reason': result.completion_reason,
                        },
                        sort_keys=True,
                    )
                )

            if result.completed:
                telemetry_logger.info(
                    'crawl: completed (%s). clearing memoization keys.',
                    result.completion_reason or 'unknown',
                )
                if memo_state.get('redis') is not None:
                    cleared = self._reset_memo_keys(
                        memo_state['redis'],
                        memo_state.get('redis_prefix', 'crawl_catalog'),
                    )
                    telemetry_logger.info(
                        'crawl: cleared %d memoization keys after completion',
                        cleared,
                    )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Catalog crawl completed: {result.completion_reason or 'done'}."
                    )
                )
                if tui:
                    tui['stop']()
                break

            if not loop:
                if tui:
                    tui['stop']()
                break

            no_new_data = (
                result.artists_created == 0
                and result.albums_created == 0
                and result.tracks_created == 0
                and len(result.failed_artist_ids) == 0
                and len(result.failed_track_ids) == 0
                and (last_missing_summary == missing_summary)
            )
            last_missing_summary = missing_summary

            if no_new_data:
                current_sleep = min(current_sleep * idle_backoff, idle_max_sleep)
                self.stdout.write(
                    self.style.WARNING(
                        f"No new data this cycle; backing off to {current_sleep:g}s."
                    )
                )
                telemetry_logger.info(
                    'crawl: idle cycle, backing off to %.1fs',
                    current_sleep,
                )
            else:
                current_sleep = loop_sleep

            if not tui:
                self.stdout.write(
                    self.style.WARNING(
                        f"Sleeping {current_sleep:g}s before next crawl cycle."
                    )
                )
            time.sleep(current_sleep)

    def _configure_file_logging(self, log_file: str | None) -> Path:
        from django.conf import settings

        if log_file:
            log_path = Path(log_file).expanduser()
        else:
            log_path = settings.BASE_DIR / 'logs' / 'crawl_catalog.log'

        log_path.parent.mkdir(parents=True, exist_ok=True)

        root_logger = logging.getLogger()
        if not any(
            isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_path
            for handler in root_logger.handlers
        ):
            handler = logging.FileHandler(log_path)
            formatter = logging.Formatter(
                '%(asctime)s %(levelname)s %(name)s %(message)s'
            )
            handler.setFormatter(formatter)
            handler.setLevel(logging.INFO)
            root_logger.addHandler(handler)
            root_logger.setLevel(logging.INFO)

        return log_path

    def _configure_memo_backend(
        self,
        telemetry_logger: logging.Logger,
        memo_ttl_seconds: float,
        reset_memo: bool,
    ) -> dict:
        from django.conf import settings

        broker_url = getattr(settings, 'CELERY_BROKER_URL', '')
        safe_broker_url = broker_url
        if broker_url:
            parsed = urlparse(broker_url)
            if parsed.password:
                netloc = parsed.username or ''
                if parsed.password:
                    netloc = f'{netloc}:****' if netloc else '****'
                if parsed.hostname:
                    netloc = f'{netloc}@{parsed.hostname}'
                if parsed.port:
                    netloc = f'{netloc}:{parsed.port}'
                safe_broker_url = parsed._replace(netloc=netloc).geturl()
        if broker_url.startswith('redis://') or broker_url.startswith('rediss://'):
            try:
                import redis
                redis_client = redis.Redis.from_url(broker_url, decode_responses=True)
                redis_client.ping()
                runtime_env = getattr(settings, 'RUNTIME_ENV', 'development')
                telemetry_logger.info('crawl: memoization using redis (%s)', safe_broker_url)
                redis_prefix = f'crawl_catalog:{runtime_env}'
                if reset_memo:
                    cleared = self._reset_memo_keys(redis_client, redis_prefix)
                    telemetry_logger.warning(
                        'crawl: reset memoization keys under %s (cleared %d keys)',
                        redis_prefix,
                        cleared,
                    )
                return {
                    'redis': redis_client,
                    'redis_prefix': redis_prefix,
                    'redis_ttl_seconds': memo_ttl_seconds,
                }
            except Exception:
                telemetry_logger.exception('crawl: failed to initialize redis memoization')
        else:
            if broker_url:
                telemetry_logger.warning('crawl: memoization disabled (non-redis broker %s)', safe_broker_url)
            else:
                telemetry_logger.warning('crawl: memoization disabled (CELERY_BROKER_URL unset)')

        return {
            'queried_genre_seeds': set(),
            'queried_artist_ids': set(),
            'hydrated_genre_seeds': set(),
        }

    def _reset_memo_keys(self, redis_client, redis_prefix: str) -> int:
        pattern = f'{redis_prefix}:*'
        cleared = 0
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=1000)
            if keys:
                redis_client.delete(*keys)
                cleared += len(keys)
            if cursor == 0:
                break
        return cleared

    def _init_tui(self):
        try:
            from rich.console import Console, Group
            from rich.live import Live
            from rich.table import Table
            from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
        except Exception:
            return None

        console = Console()
        genres_total = len(getattr(spotify_stub, 'GENRE_SEEDS', []))
        state = {
            'current_genre': '',
            'current_artist': '',
            'current_album': '',
            'genres_total': genres_total,
            'genres_done': 0,
            'genres_hydrated': 0,
            'genres_skipped': 0,
            'genres_failed': 0,
            'genre_total_artists': None,
            'genre_seen_artists': 0,
            'artist_total_albums': None,
            'artist_seen_albums': 0,
            'album_total_tracks': None,
            'album_seen_tracks': 0,
            'counts': {
                'artists_created': 0,
                'artists_updated': 0,
                'artists_skipped': 0,
                'artists_failed': 0,
                'albums_created': 0,
                'albums_updated': 0,
                'albums_skipped': 0,
                'albums_failed': 0,
                'tracks_created': 0,
                'tracks_updated': 0,
                'tracks_skipped': 0,
                'tracks_failed': 0,
            },
        }

        progress = Progress(
            TextColumn('[bold]{task.description}'),
            BarColumn(),
            TextColumn('{task.completed}/{task.total}'),
            TimeElapsedColumn(),
            transient=False,
        )
        genre_task = progress.add_task('Genres', total=genres_total or 1)
        artist_task = progress.add_task('Artists (current genre)', total=1)
        album_task = progress.add_task('Albums (current artist)', total=1)
        track_task = progress.add_task('Tracks (current album)', total=1)

        def render():
            table = Table(title='Crawl Progress', expand=True)
            table.add_column('Scope')
            table.add_column('Current')
            table.add_column('Created')
            table.add_column('Updated')
            table.add_column('Skipped')
            table.add_column('Failed')
            table.add_column('Remaining')

            def remaining(total, seen):
                if total is None:
                    return 'unknown'
                return str(max(total - seen, 0))

            table.add_row(
                'Genres',
                state['current_genre'] or '-',
                str(state['genres_done']),
                str(state['genres_hydrated']),
                str(state['genres_skipped']),
                str(state['genres_failed']),
                remaining(state['genres_total'], state['genres_done']),
            )
            table.add_row(
                'Artists',
                state['current_artist'] or '-',
                str(state['counts']['artists_created']),
                str(state['counts']['artists_updated']),
                str(state['counts']['artists_skipped']),
                str(state['counts']['artists_failed']),
                remaining(state['genre_total_artists'], state['genre_seen_artists']),
            )
            table.add_row(
                'Albums',
                state['current_album'] or '-',
                str(state['counts']['albums_created']),
                str(state['counts']['albums_updated']),
                str(state['counts']['albums_skipped']),
                str(state['counts']['albums_failed']),
                remaining(state['artist_total_albums'], state['artist_seen_albums']),
            )
            table.add_row(
                'Tracks',
                state['current_album'] or '-',
                str(state['counts']['tracks_created']),
                str(state['counts']['tracks_updated']),
                str(state['counts']['tracks_skipped']),
                str(state['counts']['tracks_failed']),
                remaining(state['album_total_tracks'], state['album_seen_tracks']),
            )
            return Group(table, progress)

        live = Live(
            renderable=render(),
            console=console,
            auto_refresh=False,
            refresh_per_second=4,
            screen=True,
        )
        live.start()

        def update_progress(event: str, **data):
            if event == 'genre_start':
                state['current_genre'] = data.get('genre', '')
                state['genre_total_artists'] = None
                state['genre_seen_artists'] = data.get('offset', 0)
            elif event == 'genre_total':
                state['genre_total_artists'] = data.get('total_artists')
            elif event == 'genre_done':
                state['genres_done'] += 1
                if data.get('hydrated'):
                    state['genres_hydrated'] += 1
                progress.update(genre_task, completed=state['genres_done'])
            elif event == 'artist_start':
                state['current_artist'] = data.get('artist', '')
            elif event == 'artist_result':
                status = data.get('status')
                if status == 'created':
                    state['counts']['artists_created'] += 1
                elif status == 'updated':
                    state['counts']['artists_updated'] += 1
                elif status == 'failed':
                    state['counts']['artists_failed'] += 1
                else:
                    state['counts']['artists_skipped'] += 1
                state['genre_seen_artists'] += 1
            elif event == 'artist_album_total':
                state['artist_total_albums'] = data.get('total_albums')
                state['artist_seen_albums'] = 0
            elif event == 'album_start':
                state['current_album'] = data.get('album', '')
            elif event == 'album_result':
                status = data.get('status')
                if status == 'created':
                    state['counts']['albums_created'] += 1
                elif status == 'updated':
                    state['counts']['albums_updated'] += 1
                elif status == 'failed':
                    state['counts']['albums_failed'] += 1
                else:
                    state['counts']['albums_skipped'] += 1
                state['artist_seen_albums'] += 1
            elif event == 'album_track_total':
                state['album_total_tracks'] = data.get('total_tracks')
                state['album_seen_tracks'] = 0
            elif event == 'track_result':
                status = data.get('status')
                if status == 'created':
                    state['counts']['tracks_created'] += 1
                elif status == 'updated':
                    state['counts']['tracks_updated'] += 1
                elif status == 'failed':
                    state['counts']['tracks_failed'] += 1
                else:
                    state['counts']['tracks_skipped'] += 1
                state['album_seen_tracks'] += 1

            if state['genre_total_artists'] is not None:
                progress.update(artist_task, total=state['genre_total_artists'], completed=state['genre_seen_artists'])
            if state['artist_total_albums'] is not None:
                progress.update(album_task, total=state['artist_total_albums'], completed=state['artist_seen_albums'])
            if state['album_total_tracks'] is not None:
                progress.update(track_task, total=state['album_total_tracks'], completed=state['album_seen_tracks'])

            live.update(render(), refresh=True)

        def stop():
            live.stop()

        return {
            'progress': update_progress,
            'stop': stop,
        }

    def _missing_summary(self) -> dict[str, int]:
        from django.db.models import Count, F, Q
        from catalog.models import Artist, Album

        hydrated_album_ids = set(
            Album.objects.annotate(track_count=Count('tracks', distinct=True))
            .filter(track_count__gte=F('total_tracks'))
            .values_list('id', flat=True)
        )

        albums_not_fully_hydrated = (
            Album.objects.annotate(track_count=Count('tracks', distinct=True))
            .filter(track_count__lt=F('total_tracks'))
            .count()
        )
        artists_not_fully_hydrated = (
            Artist.objects.annotate(
                album_count=Count('albums', distinct=True),
                hydrated_album_count=Count(
                    'albums',
                    filter=Q(albums__in=hydrated_album_ids),
                    distinct=True,
                ),
            )
            .filter(Q(album_count=0) | Q(hydrated_album_count__lt=F('album_count')))
            .count()
        )
        return {
            'artists_not_fully_hydrated': artists_not_fully_hydrated,
            'albums_not_fully_hydrated': albums_not_fully_hydrated,
        }
