"""Pick quality: seeded stations stay near their seeds; feelings describe sound, not titles."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from radio.models import Station
from radio.services import feelings, recommend
from tests.radio_support import FakeSpotify, canonical_with_alias, engine_response, sp_track

ENGINE = 'recommender.services.client.fetch_identity_recommendations'


class PickTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='radio-picks', email='picks@example.test')
        self.fake = FakeSpotify()
        patcher = mock.patch('radio.services.spotify.get_client', return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def station(self, seeds=('seed-1',), feelings=()):
        return Station.objects.create(user=self.user, name='Test', frequency=100.1, feelings=list(feelings),
                                      seeds=[{'kind': 'track', 'spotifyId': seed, 'title': 'Seed'} for seed in seeds])

    @staticmethod
    def engine_by_seed(responses, metadata=None):
        """Engine double answering per first seed id (co-occurrence) and per ranker."""
        def engine(ranker, payload, timeout=None):
            if ranker == 'metadata':
                return metadata or {'items': []}
            first = payload['seed_items'][0]['source_id']
            return responses.get(first, {'items': []})
        return engine

    @staticmethod
    def ids(result):
        return [track['spotifyId'] for track in result.tracks]

    @staticmethod
    def sources(result):
        return [track['sources'][0] for track in result.tracks]


class SeededStationTests(PickTestCase):
    def test_second_cooccurrence_hop_fills_before_any_feeling_search(self):
        # Hop 1 only finds the seed's own album (one artist); hop 2 reaches further.
        album = [canonical_with_alias(f'alb-{idx}') for idx in range(3)]
        further = [canonical_with_alias(f'far-{idx}') for idx in range(3)]
        self.fake.add(sp_track('seed-1', artist_id='toto'), *[sp_track(f'alb-{idx}', artist_id='toto') for idx in range(3)],
                      *[sp_track(f'far-{idx}', artist_id=f'far-artist-{idx}') for idx in range(3)])
        # Literal "Late Night" title matches that the old pipeline used to inject.
        self.fake.search_results['genre:chillwave'] = [sp_track('late-night', artist_id='rapper', name='Late Night Tip')]
        engine = self.engine_by_seed({'seed-1': engine_response(*album), 'alb-0': engine_response(*further)})
        with mock.patch(ENGINE, side_effect=engine):
            result = recommend.next_tracks(self.user, self.station(feelings=['🌙']), count=3)
        self.assertEqual(self.ids(result), ['alb-0', 'far-0', 'far-1'])
        self.assertEqual(self.sources(result), ['mlcore', 'mlcore:hop2', 'mlcore:hop2'])
        self.assertEqual(result.source, 'mlcore')
        self.assertNotIn('late-night', self.ids(result))
        self.assertEqual(self.fake.called('search'), [])  # seed-related picks were enough

    def test_fallback_order_metadata_then_seed_artists_then_cooccurring_artists(self):
        meta = canonical_with_alias('meta-1')
        pick = canonical_with_alias('pick-1')
        self.fake.add(sp_track('seed-1', artist_id='seed-artist', featuring=[('guest', 'Guest')]),
                      sp_track('pick-1', artist_id='co-artist'), sp_track('meta-1', artist_id='meta-artist'))
        self.fake.top = {'seed-artist': [sp_track('seed-top', artist_id='seed-artist')],
                         'guest': [sp_track('guest-top', artist_id='guest')],
                         'co-artist': [sp_track('co-top', artist_id='co-artist-2')]}
        engine = self.engine_by_seed({'seed-1': engine_response(pick)}, metadata=engine_response(meta))
        with mock.patch(ENGINE, side_effect=engine):
            result = recommend.next_tracks(self.user, self.station(), count=5)
        self.assertEqual(self.ids(result), ['pick-1', 'meta-1', 'seed-top', 'guest-top', 'co-top'])
        self.assertEqual(self.sources(result), ['mlcore', 'metadata', 'artist:seed', 'artist:seed', 'artist:cooccur'])
        self.assertEqual(result.source, 'artist')  # 3 of 5 tracks came from artist top tracks

    def test_feelings_rerank_seeded_candidates_by_genre(self):
        items = [canonical_with_alias(f'p{idx}') for idx in range(6)]
        self.fake.add(*[sp_track(f'p{idx}', artist_id=f'a{idx}') for idx in range(6)])
        self.fake.genres = {'a4': ['chillwave'], 'a5': ['ambient', 'drone'], 'a0': ['polka']}
        with mock.patch(ENGINE, side_effect=self.engine_by_seed({'seed-1': engine_response(*items)})):
            result = recommend.next_tracks(self.user, self.station(feelings=['🌙']), count=3)
        self.assertEqual(self.ids(result), ['p4', 'p5', 'p0'])
        self.assertEqual(result.source, 'mlcore')

    def test_sound_search_fills_shortfall_but_ranks_after_seed_picks(self):
        pick = canonical_with_alias('pick-1')
        self.fake.add(sp_track('pick-1', artist_id='co-artist'))
        self.fake.search_results['genre:chillwave'] = [sp_track('wave-1', artist_id='waver')]
        self.fake.genres = {'waver': ['chillwave'], 'co-artist': ['polka']}
        with mock.patch(ENGINE, side_effect=self.engine_by_seed({'seed-1': engine_response(pick)})):
            result = recommend.next_tracks(self.user, self.station(feelings=['🌙']), count=2)
        self.assertEqual(self.ids(result), ['pick-1', 'wave-1'])
        self.assertEqual(self.sources(result), ['mlcore', 'search:genre'])
        self.assertEqual(result.source, 'mlcore')  # 1–1 tie → the earliest track's source

    def test_seeded_without_feelings_searches_seed_artist_genres(self):
        self.fake.add(sp_track('seed-1', artist_id='toto'))
        self.fake.genres = {'toto': ['afropop', 'world']}
        self.fake.search_results['genre:afropop'] = [sp_track('afro-1', artist_id='afro-artist')]
        with mock.patch(ENGINE, return_value={'items': []}):
            result = recommend.next_tracks(self.user, self.station(), count=1)
        self.assertEqual((self.ids(result), self.sources(result)), (['afro-1'], ['search:genre']))
        self.assertFalse([call for call in self.fake.called('search') if 'genre:' not in call[1]])


    def test_slow_engine_leaves_time_for_seed_artists(self):
        clock = [0.0]
        album = [canonical_with_alias(f'alb-{idx}') for idx in range(3)]
        self.fake.add(sp_track('seed-1', artist_id='toto', featuring=[('bona', 'Bona')]),
                      *[sp_track(f'alb-{idx}', artist_id='toto') for idx in range(3)])
        self.fake.top = {'bona': [sp_track('bona-1', artist_id='bona')], 'toto': []}

        def slow_engine(ranker, payload, timeout=None):
            clock[0] += timeout  # every engine call runs into its timeout
            return engine_response(*album) if payload['seed_items'][0]['source_id'] == 'seed-1' else {'items': []}

        with mock.patch('radio.services.spotify.time.monotonic', side_effect=lambda: clock[0]), \
                mock.patch(ENGINE, side_effect=slow_engine):
            result = recommend.next_tracks(self.user, self.station(), count=2)
        self.assertEqual(self.ids(result), ['alb-0', 'bona-1'])
        self.assertEqual(self.sources(result), ['mlcore', 'artist:seed'])


class FeelingOnlyStationTests(PickTestCase):
    def test_genre_filters_diversify_artists_and_skip_non_music(self):
        self.fake.search_results['genre:chillwave'] = [
            sp_track('cw-1', artist_id='braids'), sp_track('cw-2', artist_id='braids'),
            {**sp_track('book', artist_id='narrator', name='Chapter 85 - Raise Your Kids'), 'duration_ms': 1_500_000}]
        self.fake.search_results['genre:downtempo'] = [sp_track('dt-1', artist_id='endless-blue')]
        self.fake.search_results['genre:"trip hop"'] = [sp_track('th-1', artist_id='nostalgia-77')]
        result = recommend.next_tracks(self.user, self.station(seeds=(), feelings=['🌙']), count=3)
        self.assertEqual(self.ids(result), ['cw-1', 'dt-1', 'th-1'])
        self.assertEqual(result.source, 'search')
        queries = [call[1] for call in self.fake.called('search')]
        self.assertTrue(all(query.startswith('genre:') for query in queries), queries)

    def test_free_text_feeling_drops_literal_title_matches_that_dont_fit(self):
        self.fake.search_results['sunday cleaning'] = [
            sp_track('literal', artist_id='polka-band', name='Sunday Cleaning'),
            sp_track('fits', artist_id='house-dj', name='Sunday Cleaning Groove'),
            sp_track('other', artist_id='indie-band', name='Open Windows')]
        self.fake.genres = {'polka-band': ['polka'], 'house-dj': ['sunday cleaning house']}
        result = recommend.next_tracks(self.user, self.station(seeds=(), feelings=['sunday cleaning']), count=3)
        self.assertEqual(self.ids(result), ['fits', 'other'])
        self.assertEqual(self.sources(result), ['search:text', 'search:text'])

    def test_second_page_when_first_page_is_spent(self):
        # A full first page (all one artist) leaves the batch short, so page 2 is fetched.
        self.fake.search_results['genre:chillhop'] = [sp_track(f'page-1-{idx}', artist_id='a1') for idx in range(10)]
        self.fake.search_results[('genre:chillhop', 'track', 10)] = [sp_track('page-2', artist_id='a2')]
        result = recommend.next_tracks(self.user, self.station(seeds=(), feelings=['😌']), count=2)
        self.assertEqual(self.ids(result), ['page-1-0', 'page-2'])

    def test_no_feelings_or_seeds_defaults_to_chill(self):
        self.fake.search_results['genre:chillhop'] = [sp_track('c1', artist_id='a1')]
        result = recommend.next_tracks(self.user, self.station(seeds=(), feelings=()), count=1)
        self.assertEqual(self.ids(result), ['c1'])


class FeelingRuleTests(SimpleTestCase):
    def test_queries_round_robin_across_feelings(self):
        queries = feelings.search_queries(['🌙', '💃'])
        self.assertEqual(queries[:4], [('genre:chillwave', 'genre'), ('genre:house', 'genre'),
                                       ('genre:downtempo', 'genre'), ('genre:"nu disco"', 'genre')])
        self.assertEqual(queries, feelings.search_queries(['🌙', '💃']))  # deterministic

    def test_year_filters_and_phrase_matching(self):
        self.assertIn(('genre:disco year:1974-1983', 'genre'), feelings.search_queries(['🪩']))
        self.assertEqual(feelings.profile_for('rainy sunday'), feelings.PROFILES['rainy'])
        self.assertEqual(feelings.search_queries(['bossa nova']),
                         [('genre:"bossa nova"', 'genre'), ('bossa nova', 'text')])

    def test_literal_title_and_non_music_detection(self):
        self.assertTrue(feelings.literal_title_match({'title': 'Late Night Tip'}, ['🌙']))
        self.assertFalse(feelings.literal_title_match({'title': 'Snow Angel'}, ['🌙']))
        self.assertFalse(feelings.looks_like_music({'title': 'Chapter 3', 'durationMs': 200000}))
        self.assertFalse(feelings.looks_like_music({'title': 'Song', 'durationMs': 30000}))
        self.assertTrue(feelings.looks_like_music({'title': 'Song', 'durationMs': 200000}))

    def test_genre_affinity(self):
        wanted = feelings.feeling_genres(['🌙'])
        self.assertGreater(feelings.genre_affinity(['dark ambient', 'drone'], wanted), 0)
        self.assertEqual(feelings.genre_affinity(['polka'], wanted), 0)

    def test_majority_source_with_earliest_tie_break(self):
        def batch(*sources):
            return [{'sources': [source]} for source in sources]
        self.assertEqual(recommend.majority_source(batch('mlcore', 'search:genre', 'search:text')), 'search')
        self.assertEqual(recommend.majority_source(batch('artist:seed', 'mlcore', 'mlcore:hop2', 'artist:cooccur')), 'artist')
        self.assertEqual(recommend.majority_source([]), 'search')


class ReviewFollowUpTests(PickTestCase):
    def test_seeds_never_outrank_discoveries(self):
        items = [canonical_with_alias(name) for name in ('p0', 'p1')]
        self.fake.add(sp_track('seed-1', artist_id='seed-artist'), sp_track('p0', artist_id='a0'), sp_track('p1', artist_id='a1'))
        self.fake.genres = {'seed-artist': ['chillwave', 'ambient']}  # the seed fits 🌙 best
        with mock.patch(ENGINE, side_effect=self.engine_by_seed({'seed-1': engine_response(*items)})):
            result = recommend.next_tracks(self.user, self.station(feelings=['🌙']), count=2)
        self.assertEqual((self.ids(result), result.source), (['p0', 'p1'], 'mlcore'))

    def test_seed_fill_ranks_last_even_with_best_affinity(self):
        self.fake.add(sp_track('seed-1', artist_id='seed-artist'), sp_track('p0', artist_id='a0'))
        self.fake.genres = {'seed-artist': ['chillwave']}
        with mock.patch(ENGINE, side_effect=self.engine_by_seed({'seed-1': engine_response(canonical_with_alias('p0'))})):
            result = recommend.next_tracks(self.user, self.station(feelings=['🌙']), count=2)
        self.assertEqual((self.ids(result), self.sources(result)), (['p0', 'seed-1'], ['mlcore', 'seed']))

    def test_seeded_station_without_genres_searches_seed_artist_by_name(self):
        self.fake.add(sp_track('seed-1', artist_id='toto', artist_name='Gerald Toto'))
        self.fake.search_results['artist:"Gerald Toto"'] = [
            sp_track('mention', artist_id='someone', artist_name='Someone', name='Gerald Toto'),
            sp_track('toto-2', artist_id='toto', artist_name='Gerald Toto')]
        with mock.patch(ENGINE, side_effect=ConnectionError('engine down')):
            result = recommend.next_tracks(self.user, self.station(), count=1, recent_ids=['seed-1'])
        self.assertEqual((self.ids(result), self.sources(result)), (['toto-2'], ['search:artist']))

    def test_seeded_station_falls_back_to_default_profile(self):
        self.fake.add(sp_track('seed-1', artist_id='toto', artist_name='Gerald Toto'))
        self.fake.search_results['genre:chillhop'] = [sp_track('chill-1', artist_id='chiller')]
        with mock.patch(ENGINE, side_effect=ConnectionError('engine down')):
            result = recommend.next_tracks(self.user, self.station(), count=1, recent_ids=['seed-1'])
        self.assertEqual(self.ids(result), ['chill-1'])  # never an empty batch → no 409 on /play

    def test_personal_station_with_seeds_uses_memory_tags_fallback(self):
        personal = Station.objects.create(user=self.user, name='Mine', kind='personal', frequency=88.7, learning=False,
                                          seeds=[{'kind': 'track', 'spotifyId': 'seed-1', 'title': 'Seed'}])
        self.fake.search_results['genre:"indie pop"'] = [sp_track('summer-1', artist_id='sunny')]
        memory = [{'songs': [], 'tags': ['summer']}]
        with mock.patch(ENGINE, side_effect=ConnectionError('down')), \
                mock.patch('vibe.memory_services.memory_recommendation_context', return_value=memory):
            result = recommend.next_tracks(self.user, personal, count=1, recent_ids=['seed-1'])
        self.assertEqual(self.ids(result), ['summer-1'])
        self.assertNotIn(('search', 'genre:chillhop', 'track'), self.fake.calls)

    def test_hop_two_keeps_user_exclusions_when_truncating(self):
        from radio.models import Exclusion

        Exclusion.objects.create(user=self.user, scope='everywhere', kind='track', value='never-this')
        items = [canonical_with_alias(f'p{idx}') for idx in range(3)]
        self.fake.add(*[sp_track(f'p{idx}', artist_id=f'a{idx}') for idx in range(3)])
        with mock.patch(ENGINE, side_effect=self.engine_by_seed({'seed-1': engine_response(*items)})) as engine, \
                mock.patch.object(recommend, 'MAX_IDENTITY_ITEMS', 2):
            recommend.next_tracks(self.user, self.station(), count=5, recent_ids=[f'r{idx}' for idx in range(10)])
        hop = [call for call in engine.call_args_list if call.args[1]['seed_items'][0]['source_id'] == 'p0'][0]
        self.assertEqual([item['source_id'] for item in hop.args[1]['exclude_items']][:1], ['never-this'])

    def test_crate_picks_keep_the_whole_budget(self):
        with mock.patch('radio.services.spotify.time.monotonic', return_value=0.0), \
                mock.patch(ENGINE, return_value={'items': []}) as engine:
            recommend.crate_track_picks(self.user, ['seed-1'], 10)
            with recommend.spotify.budget(recommend.NEXT_BUDGET_SECONDS):
                recommend.mlcore_track_ids('cooccurrence', ['seed-1'], [], 10)
        self.assertEqual(engine.call_args_list[0].kwargs['timeout'], recommend.NEXT_BUDGET_SECONDS)
        self.assertEqual(engine.call_args_list[1].kwargs['timeout'],
                         recommend.NEXT_BUDGET_SECONDS - recommend.MLCORE_RESERVE_SECONDS)


class SearchCostTests(PickTestCase):
    def test_second_page_only_for_full_first_pages(self):
        self.fake.search_results['genre:chillwave'] = [sp_track(f'cw-{idx}', artist_id='same') for idx in range(10)]
        self.fake.search_results['genre:downtempo'] = [sp_track('dt-1', artist_id='other')]
        recommend.next_tracks(self.user, self.station(seeds=(), feelings=['🌙']), count=5)
        second_page = [call for call in self.fake.calls if call[0] == 'search_page2']
        self.assertEqual([call[1] for call in second_page], ['genre:chillwave'])

    def test_many_searches_stay_within_budget(self):
        clock = [0.0]
        real_search = self.fake.search

        def slow_search(*args, **kwargs):
            clock[0] += 0.5
            return real_search(*args, **kwargs)

        self.fake.search = slow_search
        for genre in ('chillwave', 'house', 'acoustic', 'downtempo', 'nu disco', 'indie folk', '"trip hop"', '"dance pop"'):
            self.fake.search_results[f'genre:{genre}'] = [sp_track(f'{genre}-{idx}', artist_id='same') for idx in range(10)]
        with mock.patch('radio.services.spotify.time.monotonic', side_effect=lambda: clock[0]):
            recommend.next_tracks(self.user, self.station(seeds=(), feelings=['🌙', '💃', '☕']), count=10)
        searches = len(self.fake.called('search')) + len([call for call in self.fake.calls if call[0] == 'search_page2'])
        self.assertLessEqual(searches, recommend.MAX_SEARCH_QUERIES)
        self.assertLessEqual(clock[0], recommend.NEXT_BUDGET_SECONDS + 0.5)


class ArtistGenreFailureTests(PickTestCase):
    def test_refused_endpoint_is_remembered(self):
        from spotipy.exceptions import SpotifyException

        self.fake.artists = mock.Mock(side_effect=SpotifyException(403, -1, 'forbidden'))
        self.assertEqual(recommend.spotify.artist_genres(['a1']), {})
        self.assertEqual(recommend.spotify.artist_genres(['a2', 'a3']), {})
        self.assertEqual(self.fake.artists.call_count, 1)
        self.assertFalse(recommend.spotify.breaker_open())

    def test_failed_ids_are_negative_cached(self):
        from spotipy.exceptions import SpotifyException

        self.fake.artists = mock.Mock(side_effect=SpotifyException(404, -1, 'missing'))
        recommend.spotify.artist_genres(['a1'])
        self.assertEqual(recommend.spotify.artist_genres(['a1']), {'a1': []})
        self.assertEqual(self.fake.artists.call_count, 1)


class MusicFilterTests(SimpleTestCase):
    def test_part_titles_are_songs_unless_long(self):
        self.assertTrue(feelings.looks_like_music({'title': 'Part 2', 'durationMs': 240000}))
        self.assertFalse(feelings.looks_like_music({'title': 'Teil 3 - Der Roman', 'durationMs': 9 * 60000}))
        self.assertFalse(feelings.looks_like_music({'title': 'Kapitel 12', 'durationMs': 200000}))

    def test_long_pieces_allowed_for_calm_profiles(self):
        long_piece = {'title': 'Music for Airports 1/1', 'durationMs': 17 * 60000}
        self.assertTrue(feelings.looks_like_music(long_piece, max_duration_ms=feelings.max_duration_ms(['😴'])))
        self.assertFalse(feelings.looks_like_music(long_piece, max_duration_ms=feelings.max_duration_ms(['💃'])))
