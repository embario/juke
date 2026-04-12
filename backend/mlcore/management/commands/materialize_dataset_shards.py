from django.core.management.base import BaseCommand, CommandError

from mlcore.services.dataset_orchestration import (
    configured_dataset_max_shards_per_run,
    configured_dataset_shard_parallelism,
    get_dataset_orchestration_service,
    validate_dataset_worker_capacity,
)


class Command(BaseCommand):
    help = 'Materialize dataset artifact shards and emit an orchestration plan for parallel ingestion.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--provider',
            required=True,
            help='Dataset provider name, for example listenbrainz.',
        )
        parser.add_argument(
            '--archive-path',
            default='',
            help='Path to the provider archive to materialize. Defaults to the provider-configured full archive.',
        )
        parser.add_argument(
            '--source-version',
            default='',
            help='Optional explicit source-version label. Defaults to the archive filename.',
        )
        parser.add_argument(
            '--output-root',
            default='',
            help='Root directory where shard trees are written. Defaults to the provider-configured shard root.',
        )
        parser.add_argument(
            '--shard-parallelism',
            type=int,
            default=configured_dataset_shard_parallelism(),
            help='Target shard fan-out for one orchestrated ingestion run.',
        )
        parser.add_argument(
            '--max-shards-per-run',
            type=int,
            default=configured_dataset_max_shards_per_run() or 0,
            help='Optional limit on scheduled shards for one orchestrated run. Use 0 for all shards.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Replace an existing shard tree for this source version.',
        )

    def handle(self, *args, **options):
        validate_dataset_worker_capacity(int(options['shard_parallelism']))
        service = get_dataset_orchestration_service(options['provider'])
        archive_path = str(options['archive_path'] or '').strip() or service.configured_archive_path() or ''
        if not archive_path:
            raise CommandError('archive-path is required or the provider must have a configured default archive path')

        result = service.materialize_shards(
            archive_path,
            source_version=str(options['source_version'] or '').strip() or None,
            shard_root=str(options['output_root'] or '').strip() or None,
            force=bool(options['force']),
            shard_parallelism=int(options['shard_parallelism']),
            max_shards_per_run=(
                int(options['max_shards_per_run'])
                if int(options['max_shards_per_run']) > 0
                else None
            ),
        )
        self.stdout.write(
            (
                'provider={provider} source_version={source_version} shards={shards} bytes={bytes} '
                'shard_parallelism={shard_parallelism} max_shards_per_run={max_shards_per_run} '
                'output={output} manifest={manifest} orchestration={orchestration}'
            ).format(
                provider=result.provider,
                source_version=result.source_version,
                shards=result.shard_count,
                bytes=result.total_uncompressed_bytes,
                shard_parallelism=result.shard_parallelism,
                max_shards_per_run=result.max_shards_per_run or 'all',
                output=result.output_root,
                manifest=result.manifest_path,
                orchestration=result.orchestration_path,
            )
        )
