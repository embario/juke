from django.core.management.base import BaseCommand

from mlcore.services.canonical_items import materialize_track_aliases


class Command(BaseCommand):
    help = 'Materialize MLCore canonical item aliases from shared catalog track identifiers.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-version',
            default='',
            help='Optional source/corpus version label to stamp on newly-created aliases.',
        )

    def handle(self, *args, **options):
        result = materialize_track_aliases(source_version=options['source_version'])
        self.stdout.write(
            self.style.SUCCESS(
                'canonical aliases materialized: '
                f'created={result.created_count} existing={result.existing_count} '
                f'conflicts={result.conflict_count}'
            )
        )
        for conflict in result.conflicts[:20]:
            self.stdout.write(
                self.style.WARNING(
                    'conflict '
                    f'{conflict.source}:{conflict.resource_type}:{conflict.source_id} '
                    f'existing={conflict.existing_canonical_item_id} '
                    f'desired={conflict.desired_canonical_item_id} '
                    f'reason={conflict.reason}'
                )
            )
        if result.conflict_count > 20:
            self.stdout.write(self.style.WARNING(f'... {result.conflict_count - 20} more conflicts omitted'))
