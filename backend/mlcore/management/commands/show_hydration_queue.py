import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from mlcore.models import ProviderHydrationItem
from mlcore.services.provider_hydration import listen_popularity


class Command(BaseCommand):
    help = 'Print the next pending Spotify hydration items in claim order, with their priority and listen score.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--provider', default='spotify')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        if options['limit'] < 1:
            raise CommandError('--limit must be greater than zero.')
        now = timezone.now()
        items = list(
            ProviderHydrationItem.objects.filter(provider=options['provider'], status__in=['pending', 'retry'])
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .order_by('priority', 'id')[: options['limit']]
        )
        scores = listen_popularity({item.canonical_item_id for item in items})
        rows = [
            {
                'position': position,
                'id': item.id,
                'priority': item.priority,
                'listen_score': round(scores.get(item.canonical_item_id, 0.0), 3),
                'identifier': item.identifier,
                'canonical_item_id': str(item.canonical_item_id),
                'status': item.status,
            }
            for position, item in enumerate(items, start=1)
        ]
        if options['json']:
            self.stdout.write(json.dumps(rows, indent=2))
            return
        for row in rows:
            self.stdout.write(
                f"{row['position']:>3}. priority={row['priority']:<3} score={row['listen_score']:<8} "
                f"{row['identifier']} item={row['id']} canonical={row['canonical_item_id']} {row['status']}"
            )
        if not rows:
            self.stdout.write('No pending items.')
