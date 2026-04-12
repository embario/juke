from django.core.management.base import BaseCommand

from mlcore.services.listenbrainz_source import (
    configured_max_incrementals_per_run,
    sync_listenbrainz_remote_dumps,
)


class Command(BaseCommand):
    help = 'Discover, download, and import new ListenBrainz full/incremental dumps.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-incrementals',
            type=int,
            default=configured_max_incrementals_per_run(),
            help='Maximum incremental releases to import in one run.',
        )

    def handle(self, *args, **options):
        result = sync_listenbrainz_remote_dumps(
            max_incrementals_per_run=options['max_incrementals'],
        )
        self.stdout.write(
            'status={status} policy={policy} full={full} incrementals={incrementals} downloads={downloads}'.format(
                status=result.status,
                policy=result.policy_classification,
                full=result.full_source_version or '-',
                incrementals=','.join(result.incremental_source_versions) or '-',
                downloads=','.join(result.downloaded_paths) or '-',
            )
        )
