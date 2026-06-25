import os
import uuid
from unittest import mock, skipIf

from pydantic import ValidationError

try:
    from django.test import SimpleTestCase
except ModuleNotFoundError:  # pragma: no cover - standalone recommender-engine image
    from unittest import TestCase as SimpleTestCase

os.environ.setdefault('POSTGRES_PORT', '5432')

try:
    from recommender_engine.app import main as engine_main
except Exception:  # pragma: no cover - backend image may omit engine-serving deps
    engine_main = None


@skipIf(engine_main is None, 'recommender engine serving dependencies are not installed')
class ResolveEndpointTests(SimpleTestCase):

    resolved_spotify_id = '0VjIjW4GlUZAMYd2vXMi3b'
    missing_spotify_id = '1VjIjW4GlUZAMYd2vXMi3b'
    conflict_spotify_id = '2VjIjW4GlUZAMYd2vXMi3b'
    seed_spotify_id = '3VjIjW4GlUZAMYd2vXMi3b'
    exclude_spotify_id = '4VjIjW4GlUZAMYd2vXMi3b'

    def test_resolve_returns_resolved_unresolved_conflict_and_invalid_items(self):
        resolved_id = uuid.uuid4()
        conflict_id = uuid.uuid4()

        def fake_run_query(sql, params=None):
            if 'mlcore_canonical_alias_materialization_run' in sql:
                return [{
                    'training_run_id': None,
                    'training_version': 'training-v1',
                    'identity_graph_run_id': None,
                    'identity_graph_version': 'identity-v1',
                    'identity_graph_algorithm_version': 'canonical-alias-v2',
                }]
            self.assertIn('mlcore_canonical_item_alias', sql)
            self.assertIn('unnest', sql)
            self.assertIn('redirect_chain', sql)
            self.assertEqual(
                params,
                [
                    ['spotify', 'spotify', 'spotify'],
                    ['track', 'track', 'track'],
                    [self.resolved_spotify_id, self.missing_spotify_id, self.conflict_spotify_id],
                ],
            )
            return [
                {
                    'source': 'spotify',
                    'resource_type': 'track',
                    'source_id': self.resolved_spotify_id,
                    'status': 'active',
                    'canonical_item_id': resolved_id,
                    'canonical_key': 'recording_mbid:abc',
                    'item_type': 'recording_mbid',
                },
                {
                    'source': 'spotify',
                    'resource_type': 'track',
                    'source_id': self.conflict_spotify_id,
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
                    source_id=f' spotify:track:{self.resolved_spotify_id} ',
                ),
                engine_main.ResolveRequestItem(
                    source='spotify',
                    resource_type='track',
                    source_id=self.missing_spotify_id,
                ),
                engine_main.ResolveRequestItem(
                    source='spotify',
                    resource_type='track',
                    source_id=self.conflict_spotify_id,
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
        self.assertEqual(len(items), 3)
        self.assertEqual(response.versions.identity_graph_version, 'identity-v1')
        self.assertEqual(response.request_id, request.request_id)

    def test_rejects_unsupported_or_invalid_identity_contracts(self):
        with self.assertRaises(ValidationError):
            engine_main.ResolveRequestItem(source='juke_catalog', resource_type='track', source_id='local-id')
        with self.assertRaises(ValidationError):
            engine_main.ResolveRequestItem(source='spotify', resource_type='recording', source_id=self.resolved_spotify_id)
        with self.assertRaises(ValidationError):
            engine_main.ResolveRequestItem(source='spotify', resource_type='track', source_id='invalid')

    def test_identity_request_deduplicates_and_limits_items(self):
        item = engine_main.ResolveRequestItem(
            source='spotify', resource_type='track', source_id=self.resolved_spotify_id,
        )
        request = engine_main.IdentityBaselineRequest(seed_items=[item, item])
        self.assertEqual(len(request.seed_items), 1)

        with self.assertRaises(ValidationError):
            engine_main.IdentityBaselineRequest(seed_items=[item] * 101)
        with self.assertRaises(ValidationError):
            engine_main.IdentityBaselineRequest(seed_items=[item], exclude_items=[item] * 101)

    def test_identity_cooccurrence_resolves_external_seeds_before_ranking(self):
        seed_id = uuid.uuid4()
        exclude_id = uuid.uuid4()
        candidate_id = uuid.uuid4()

        def fake_run_query(sql, params=None):
            if 'mlcore_canonical_item_alias' in sql:
                source_ids = params[2]
                rows = []
                if self.seed_spotify_id in source_ids:
                    rows.append({
                        'source': 'spotify',
                        'resource_type': 'track',
                        'source_id': self.seed_spotify_id,
                        'status': 'active',
                        'canonical_item_id': seed_id,
                        'canonical_key': 'recording_mbid:seed',
                        'item_type': 'recording_mbid',
                    })
                if self.exclude_spotify_id in source_ids:
                    rows.append({
                        'source': 'spotify',
                        'resource_type': 'track',
                        'source_id': self.exclude_spotify_id,
                        'status': 'active',
                        'canonical_item_id': exclude_id,
                        'canonical_key': 'recording_mbid:exclude',
                        'item_type': 'recording_mbid',
                    })
                return rows
            if 'mlcore_canonical_alias_materialization_run' in sql:
                return [{
                    'training_run_id': None,
                    'training_version': 'training-v1',
                    'identity_graph_run_id': None,
                    'identity_graph_version': 'identity-v1',
                    'identity_graph_algorithm_version': 'canonical-alias-v2',
                }]
            if 'mlcore_item_cooccurrence' in sql:
                self.assertEqual(params, [[seed_id]])
                self.assertIn('mlcore_canonical_item_redirect', sql)
                return [
                    {'neighbour': candidate_id, 'pmi_score': 2.5, 'co_count': 4},
                    {'neighbour': exclude_id, 'pmi_score': 9.0, 'co_count': 1},
                ]
            raise AssertionError(f'Unexpected SQL: {sql}')

        request = engine_main.IdentityBaselineRequest(
            seed_items=[
                engine_main.ResolveRequestItem(
                    source='spotify',
                    resource_type='track',
                    source_id=self.seed_spotify_id,
                ),
                engine_main.ResolveRequestItem(
                    source='spotify',
                    resource_type='track',
                    source_id=self.missing_spotify_id,
                ),
            ],
            exclude_items=[
                engine_main.ResolveRequestItem(
                    source='spotify',
                    resource_type='track',
                    source_id=self.exclude_spotify_id,
                ),
            ],
            limit=10,
        )

        with mock.patch.object(engine_main, '_run_query', side_effect=fake_run_query):
            response = engine_main.recommend_cooccurrence_identity(request)

        self.assertEqual(response.ranker, 'cooccurrence')
        self.assertEqual(response.requested_seed_count, 2)
        self.assertEqual(response.resolved_seed_count, 1)
        self.assertEqual(response.seed_count, 1)
        self.assertEqual([item.canonical_item_id for item in response.items], [candidate_id])
        self.assertEqual(response.items[0].components['co_count_sum'], 4.0)
        self.assertEqual(len(response.unresolved_seed_items), 1)
        self.assertEqual(response.unresolved_seed_items[0].status, 'unresolved')
        self.assertEqual(response.unresolved_exclude_items, [])
        self.assertEqual(response.versions.training_version, 'training-v1')
        self.assertEqual(response.versions.identity_graph_version, 'identity-v1')
        self.assertEqual(response.versions.identity_graph_algorithm_version, 'canonical-alias-v2')

    def test_identity_recommendation_with_no_resolved_seeds_returns_empty_response(self):
        request = engine_main.IdentityBaselineRequest(
            seed_items=[
                engine_main.ResolveRequestItem(
                    source='spotify',
                    resource_type='track',
                    source_id=self.missing_spotify_id,
                ),
            ],
            limit=10,
        )

        def fake_run_query(sql, params=None):
            if 'mlcore_canonical_item_alias' in sql:
                return []
            if 'mlcore_canonical_alias_materialization_run' in sql:
                return [{}]
            raise AssertionError(f'Unexpected SQL: {sql}')

        with mock.patch.object(engine_main, '_run_query', side_effect=fake_run_query):
            response = engine_main.recommend_metadata_identity(request)

        self.assertEqual(response.items, [])
        self.assertEqual(response.ranker, 'metadata')
        self.assertEqual(response.requested_seed_count, 1)
        self.assertEqual(response.resolved_seed_count, 0)
        self.assertEqual(response.unresolved_seed_items[0].status, 'unresolved')

    def test_reports_unresolved_exclusions(self):
        request = engine_main.IdentityBaselineRequest(
            seed_items=[engine_main.ResolveRequestItem(
                source='spotify', resource_type='track', source_id=self.seed_spotify_id,
            )],
            exclude_items=[engine_main.ResolveRequestItem(
                source='spotify', resource_type='track', source_id=self.missing_spotify_id,
            )],
        )

        def fake_run_query(sql, params=None):
            if 'mlcore_canonical_item_alias' in sql:
                if self.seed_spotify_id in params[2]:
                    return [{
                        'source': 'spotify', 'resource_type': 'track', 'source_id': self.seed_spotify_id,
                        'status': 'active', 'canonical_item_id': uuid.uuid4(),
                        'canonical_key': 'recording_mbid:seed', 'item_type': 'recording_mbid',
                    }]
                return []
            if 'mlcore_item_cooccurrence' in sql:
                return []
            if 'mlcore_canonical_alias_materialization_run' in sql:
                return [{}]
            raise AssertionError(f'Unexpected SQL: {sql}')

        with mock.patch.object(engine_main, '_run_query', side_effect=fake_run_query):
            response = engine_main.recommend_cooccurrence_identity(request)

        self.assertEqual(len(response.unresolved_exclude_items), 1)
        self.assertEqual(response.unresolved_exclude_items[0].source_id, self.missing_spotify_id)
