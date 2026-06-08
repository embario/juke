import os
import uuid
from unittest import mock, skipIf

from django.test import SimpleTestCase

os.environ.setdefault('POSTGRES_PORT', '5432')

try:
    from recommender_engine.app import main as engine_main
except Exception:  # pragma: no cover - backend image may omit engine-serving deps
    engine_main = None


@skipIf(engine_main is None, 'recommender engine serving dependencies are not installed')
class ResolveEndpointTests(SimpleTestCase):

    def test_resolve_returns_resolved_unresolved_conflict_and_invalid_items(self):
        resolved_id = uuid.uuid4()
        conflict_id = uuid.uuid4()

        def fake_run_query(sql, params):
            self.assertIn('mlcore_canonical_item_alias', sql)
            self.assertIn('unnest', sql)
            self.assertEqual(
                params,
                [
                    ['spotify', 'spotify', 'spotify'],
                    ['track', 'track', 'track'],
                    ['spotify-conflict', 'spotify-missing', 'spotify-resolved'],
                ],
            )
            return [
                {
                    'source': 'spotify',
                    'resource_type': 'track',
                    'source_id': 'spotify-resolved',
                    'status': 'active',
                    'canonical_item_id': resolved_id,
                    'canonical_key': 'recording_mbid:abc',
                    'item_type': 'recording_mbid',
                },
                {
                    'source': 'spotify',
                    'resource_type': 'track',
                    'source_id': 'spotify-conflict',
                    'status': 'conflict',
                    'canonical_item_id': conflict_id,
                    'canonical_key': 'recording_mbid:def',
                    'item_type': 'recording_mbid',
                },
            ]

        request = engine_main.ResolveRequest(
            items=[
                engine_main.ResolveRequestItem(
                    source=' Spotify ',
                    resource_type=' Track ',
                    source_id=' spotify-resolved ',
                ),
                engine_main.ResolveRequestItem(
                    source='spotify',
                    resource_type='track',
                    source_id='spotify-missing',
                ),
                engine_main.ResolveRequestItem(
                    source='spotify',
                    resource_type='track',
                    source_id='spotify-conflict',
                ),
                engine_main.ResolveRequestItem(
                    source='spotify',
                    resource_type='track',
                    source_id='   ',
                ),
            ]
        )

        with mock.patch.object(engine_main, '_run_query', side_effect=fake_run_query):
            response = engine_main.resolve(request)

        items = response.items
        self.assertEqual(items[0].status, 'resolved')
        self.assertEqual(items[0].canonical_item_id, resolved_id)
        self.assertEqual(items[0].canonical_key, 'recording_mbid:abc')
        self.assertEqual(items[1].status, 'unresolved')
        self.assertIsNone(items[1].canonical_item_id)
        self.assertEqual(items[2].status, 'conflict')
        self.assertEqual(items[2].canonical_item_id, conflict_id)
        self.assertEqual(items[3].status, 'invalid')
