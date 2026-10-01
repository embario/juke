from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from radio.models import Exclusion, ListeningEvent, Station, TrackReaction
from radio.services import recommend, signals, spotify, suggestions
from tests.radio_support import FakeSpotify, canonical_with_alias, engine_response, sp_track

ENGINE = 'recommender.services.client.fetch_identity_recommendations'


class RadioTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='radio-unit', email='radio-unit@example.test')
        self.fake = FakeSpotify()
        patcher = mock.patch('radio.services.spotify.get_client', return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def station(self, **kwargs):
        defaults = {'user': self.user, 'name': 'Test', 'kind': 'custom', 'frequency': 100.1,
                    'seeds': [{'kind': 'track', 'spotifyId': 'seed-1', 'title': 'Seed', 'subtitle': 'Seed Artist'}],
                    'feelings': []}
        defaults.update(kwargs)
        return Station.objects.create(**defaults)

    def event(self, track_id, event='play', minutes_ago=0, station=None):
        row = ListeningEvent.objects.create(user=self.user, spotify_track_id=track_id, event=event, station=station)
        ListeningEvent.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
        return row


class SpotifyHydrationTests(RadioTestCase):
    def test_track_payload_matches_contract(self):
        self.fake.add(sp_track('t1', artist_id='ar1', artist_name='Ana'))
        track = spotify.get_tracks(['t1'])['t1']
        self.assertEqual(set(track), {'spotifyId', 'uri', 'title', 'artist', 'artistId', 'album', 'albumId', 'artworkUrl',
                                      'durationMs'})
        self.assertEqual((track['artistId'], track['albumId'], track['artworkUrl']), ('ar1', 'album-1', 'https://img.test/album-1.jpg'))

    def test_hydration_is_batched_and_cached(self):
        self.fake.add(*[sp_track(f't{idx}') for idx in range(60)])
        ids = [f't{idx}' for idx in range(60)]
        self.assertEqual(len(spotify.get_tracks(ids)), 60)
        self.assertEqual([len(call[1]) for call in self.fake.called('tracks')], [50, 10])
        spotify.get_tracks(ids)
        self.assertEqual(len(self.fake.called('tracks')), 2)

    def test_batch_failure_falls_back_to_single_lookups(self):
        self.fake.fail_batch = True
        self.fake.add(sp_track('t1'), sp_track('t2'))
        self.assertEqual(set(spotify.get_tracks(['t1', 't2', 'missing'])), {'t1', 't2'})
        self.assertEqual(len(self.fake.called('track')), 3)

    def test_unavailable_client_returns_empty(self):
        with mock.patch('radio.services.spotify.get_client', return_value=None):
            self.assertEqual(spotify.get_tracks(['x']), {})
            self.assertEqual(spotify.search_tracks('late night'), [])

    def test_stub_client_shapes(self):
        stub = spotify.StubSpotify()
        with mock.patch('radio.services.spotify.get_client', return_value=stub):
            self.assertTrue(spotify.get_tracks(['abc'])['abc']['title'])
            self.assertEqual(len(spotify.artist_top_tracks('artist-xyz')), 5)
            self.assertEqual(len(spotify.album_track_ids('album-xyz')), 3)
            self.assertTrue(spotify.search_tracks('rain'))


class AliasLookupTests(RadioTestCase):
    def test_maps_canonical_ids_to_active_spotify_aliases(self):
        good = canonical_with_alias('sp-good')
        inactive = canonical_with_alias('sp-inactive', status='inactive')
        other_source = canonical_with_alias('mbid-1', source='musicbrainz')
        mapping = recommend.spotify_ids_for_canonical([str(good.id), str(inactive.id), str(other_source.id)])
        self.assertEqual(list(mapping), [str(good.id)])
        self.assertEqual(mapping[str(good.id)]['spotifyId'], 'sp-good')
        self.assertEqual(mapping[str(good.id)]['evidence']['name'], 'Evidence sp-good')

    def test_mlcore_ids_keep_engine_rank_order_and_payload(self):
        first, second = canonical_with_alias('sp-1'), canonical_with_alias('sp-2')
        with mock.patch(ENGINE, return_value=engine_response(second, first)) as engine:
            pairs = recommend.mlcore_track_ids('cooccurrence', ['seed'], ['old'], 12)
        self.assertEqual([track_id for track_id, _ in pairs], ['sp-2', 'sp-1'])
        ranker, payload = engine.call_args.args
        self.assertEqual(ranker, 'cooccurrence')
        self.assertEqual(payload['seed_items'], [{'source': 'spotify', 'resource_type': 'track', 'source_id': 'seed'}])
        self.assertEqual(payload['exclude_items'][0]['source_id'], 'old')
        self.assertEqual(payload['limit'], 12)

    def test_engine_failure_returns_empty(self):
        with mock.patch(ENGINE, side_effect=ConnectionError('down')):
            self.assertEqual(recommend.mlcore_track_ids('cooccurrence', ['seed'], [], 5), [])


class PipelineTests(RadioTestCase):
    def test_mlcore_primary_source_with_hydration(self):
        items = [canonical_with_alias(f'ml-{idx}') for idx in range(3)]
        self.fake.add(*[sp_track(f'ml-{idx}', artist_id=f'ar{idx}', artist_name=f'A{idx}') for idx in range(3)])
        with mock.patch(ENGINE, return_value=engine_response(*items)):
            result = recommend.next_tracks(self.user, self.station(), count=3)
        self.assertEqual(result.source, 'mlcore')
        self.assertEqual([track['spotifyId'] for track in result.tracks], ['ml-0', 'ml-1', 'ml-2'])
        self.assertEqual(result.tracks[0]['artworkUrl'], 'https://img.test/album-1.jpg')

    def test_unhydratable_mlcore_track_uses_alias_evidence(self):
        item = canonical_with_alias('ml-x')
        with mock.patch(ENGINE, return_value=engine_response(item)):
            result = recommend.next_tracks(self.user, self.station(), count=1)
        self.assertEqual(result.tracks[0]['title'], 'Evidence ml-x')
        self.assertEqual(result.tracks[0]['artist'], 'Evidence Artist')

    def test_filters_exclusions_recent_history_and_request_recent_ids(self):
        station = self.station()
        names = ['blocked-track', 'blocked-artist', 'played', 'client-recent', 'text-hit', 'keeper']
        items = [canonical_with_alias(name) for name in names]
        self.fake.add(sp_track('blocked-track', artist_id='a1'), sp_track('blocked-artist', artist_id='bad-artist'),
                      sp_track('played', artist_id='a3'), sp_track('client-recent', artist_id='a4'),
                      sp_track('text-hit', artist_id='a5', name='Christmas Song'), sp_track('keeper', artist_id='a6'))
        Exclusion.objects.create(user=self.user, station=station, scope='station', kind='track', value='blocked-track')
        Exclusion.objects.create(user=self.user, station=None, scope='everywhere', kind='artist', value='bad-artist')
        Exclusion.objects.create(user=self.user, station=None, scope='everywhere', kind='text', value='christmas')
        other = self.station(name='Other', frequency=90.1)
        Exclusion.objects.create(user=self.user, station=other, scope='station', kind='track', value='keeper')
        self.event('played', 'complete')
        with mock.patch(ENGINE, return_value=engine_response(*items)) as engine:
            result = recommend.next_tracks(self.user, station, count=3, recent_ids=['client-recent'])
        self.assertEqual([track['spotifyId'] for track in result.tracks][:1], ['keeper'])
        returned = {track['spotifyId'] for track in result.tracks}
        self.assertFalse(returned & set(names[:5]))
        excluded = {item['source_id'] for item in engine.call_args_list[0].args[1]['exclude_items']}
        self.assertTrue({'played', 'client-recent', 'blocked-track'} <= excluded)

    def test_excludes_artist_by_name_label(self):
        station = self.station()
        Exclusion.objects.create(user=self.user, scope='everywhere', kind='artist', value='Some Artist')
        item = canonical_with_alias('ev-only', evidence={'name': 'x', 'artists': ['Some Artist']})
        with mock.patch(ENGINE, return_value=engine_response(item)):
            self.assertEqual(recommend.next_tracks(self.user, station, count=1).tracks, [])

    def test_recent_history_limit(self):
        for idx in range(60):
            self.event(f'h{idx}', minutes_ago=60 - idx)
        recent = signals.recent_track_ids(self.user)
        self.assertEqual(len(recent), 50)
        self.assertEqual(recent[0], 'h59')
        self.assertNotIn('h0', recent)

    def test_dedupes_artists_within_batch_when_possible(self):
        items = [canonical_with_alias(name) for name in ('s1', 's2', 'o1')]
        self.fake.add(sp_track('s1', artist_id='same'), sp_track('s2', artist_id='same'), sp_track('o1', artist_id='other'))
        with mock.patch(ENGINE, return_value=engine_response(*items)):
            result = recommend.next_tracks(self.user, self.station(), count=2)
        self.assertEqual([track['spotifyId'] for track in result.tracks], ['s1', 'o1'])

    def test_allows_artist_repeats_rather_than_coming_up_short(self):
        items = [canonical_with_alias(name) for name in ('s1', 's2')]
        self.fake.add(sp_track('s1', artist_id='same'), sp_track('s2', artist_id='same'))
        with mock.patch(ENGINE, return_value=engine_response(*items)):
            result = recommend.next_tracks(self.user, self.station(feelings=[]), count=2)
        self.assertEqual({track['spotifyId'] for track in result.tracks}, {'s1', 's2'})

    def test_falls_back_to_metadata_ranker(self):
        item = canonical_with_alias('meta-1')
        self.fake.add(sp_track('meta-1'))

        def engine(ranker, payload):
            return {'items': []} if ranker == 'cooccurrence' else engine_response(item)

        with mock.patch(ENGINE, side_effect=engine):
            result = recommend.next_tracks(self.user, self.station(), count=1)
        self.assertEqual((result.source, result.tracks[0]['spotifyId']), ('metadata', 'meta-1'))

    def test_falls_back_to_seed_artist_top_tracks(self):
        self.fake.add(sp_track('seed-1', artist_id='seed-artist'))
        self.fake.top['seed-artist'] = [sp_track('top-1', artist_id='seed-artist'), sp_track('seed-1', artist_id='seed-artist')]
        with mock.patch(ENGINE, return_value={'items': []}):
            result = recommend.next_tracks(self.user, self.station(), count=1)
        self.assertEqual((result.source, result.tracks[0]['spotifyId']), ('artist', 'top-1'))

    def test_falls_back_to_feeling_keyword_search(self):
        self.fake.search_results['late night'] = [sp_track('night-1')]
        station = self.station(seeds=[], feelings=['🌙'])
        with mock.patch(ENGINE, side_effect=ConnectionError('down')):
            result = recommend.next_tracks(self.user, station, count=1)
        self.assertEqual((result.source, result.tracks[0]['spotifyId']), ('search', 'night-1'))
        self.assertIn(('search', 'late night', 'track'), self.fake.calls)

    def test_free_text_feelings_are_search_terms(self):
        self.fake.search_results['sunday cleaning'] = [sp_track('clean-1')]
        result = recommend.next_tracks(self.user, self.station(seeds=[], feelings=['sunday cleaning']), count=1)
        self.assertEqual(result.tracks[0]['spotifyId'], 'clean-1')

    def test_last_resort_plays_seed_tracks(self):
        self.fake.add(sp_track('seed-1', artist_id='lonely'))
        with mock.patch(ENGINE, return_value={'items': []}):
            result = recommend.next_tracks(self.user, self.station(), count=1)
        self.assertEqual((result.source, result.tracks[0]['spotifyId']), ('seed', 'seed-1'))

    def test_artist_and_album_seeds_expand_to_tracks(self):
        self.fake.top['ar'] = [sp_track('ar-top-1', artist_id='ar')]
        self.fake.albums['al'] = ['al-1', 'al-2']
        station = self.station(seeds=[{'kind': 'artist', 'spotifyId': 'ar', 'title': 'Artist'},
                                      {'kind': 'album', 'spotifyId': 'al', 'title': 'Album'}])
        with mock.patch(ENGINE, return_value={'items': []}) as engine:
            recommend.next_tracks(self.user, station, count=1)
        seeds = [item['source_id'] for item in engine.call_args_list[0].args[1]['seed_items']]
        self.assertEqual(seeds, ['ar-top-1', 'al-1', 'al-2'])

    def test_personal_station_learns_from_positive_signals_and_memories(self):
        personal = self.station(kind='personal', seeds=[], frequency=88.7)
        self.event('done', 'complete')
        self.event('saved', 'save')
        self.event('heard', 'recognized')
        self.event('skipped-only', 'skip')
        self.event('disliked', 'complete')
        self.event('disliked', 'less')
        TrackReaction.objects.create(user=self.user, spotify_track_id='loved', reactions=['🔥'])
        memory_signals = [{'songs': [{'provider': 'spotify', 'providerTrackID': 'memory-song'},
                                     {'provider': 'apple', 'providerTrackID': 'apple-song'}], 'tags': ['summer']}]
        with mock.patch('vibe.memory_services.memory_recommendation_context', return_value=memory_signals), \
                mock.patch(ENGINE, return_value={'items': []}) as engine:
            recommend.next_tracks(self.user, personal, count=1)
        seeds = {item['source_id'] for item in engine.call_args_list[0].args[1]['seed_items']}
        self.assertEqual(seeds, {'done', 'saved', 'heard', 'loved', 'memory-song'})

    def test_personal_station_not_learning_uses_station_seeds(self):
        personal = self.station(kind='personal', learning=False, frequency=88.7)
        self.event('done', 'complete')
        with mock.patch(ENGINE, return_value={'items': []}) as engine:
            recommend.next_tracks(self.user, personal, count=1)
        seeds = [item['source_id'] for item in engine.call_args_list[0].args[1]['seed_items']]
        self.assertEqual(seeds, ['seed-1'])


class SuggestionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='radio-suggest', email='s@example.test')

    def make(self, name, feelings, freq):
        return Station.objects.create(user=self.user, name=name, frequency=freq, feelings=feelings)

    def test_suggests_better_matching_station(self):
        current = self.make('Morning', ['☕'], 90.1)
        night = self.make('Night', ['🌙', 'rainy day'], 100.1)
        suggestion = suggestions.suggest_station(['🌙', '🌧️'], current, [current, night])
        self.assertEqual(suggestion, {'stationId': str(night.id), 'name': 'Night', 'matched': ['🌙', '🌧️']})

    def test_tie_with_current_station_returns_none(self):
        current = self.make('Night A', ['🌙'], 90.1)
        other = self.make('Night B', ['late night'], 100.1)
        self.assertIsNone(suggestions.suggest_station(['🌙'], current, [current, other]))

    def test_tie_between_candidates_returns_none(self):
        one, two = self.make('One', ['🔥'], 90.1), self.make('Two', ['hype'], 100.1)
        self.assertIsNone(suggestions.suggest_station(['🔥'], None, [one, two]))

    def test_no_reactions_or_no_match(self):
        one = self.make('One', ['🔥'], 90.1)
        self.assertIsNone(suggestions.suggest_station([], None, [one]))
        self.assertIsNone(suggestions.suggest_station(['😴'], None, [one]))


class SessionTests(RadioTestCase):
    def test_session_starts_after_last_thirty_minute_gap(self):
        self.event('old', minutes_ago=120)
        first = self.event('a', minutes_ago=50)
        self.event('b', minutes_ago=25)
        self.event('c', minutes_ago=1)
        session = signals.current_session_events(self.user)
        self.assertEqual([event.spotify_track_id for event in session], ['a', 'b', 'c'])
        self.assertEqual(session[0].pk, first.pk)
