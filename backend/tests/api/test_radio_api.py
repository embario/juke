import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from social_django.models import UserSocialAuth
from spotipy.exceptions import SpotifyException

from radio.models import Exclusion, ListeningEvent, Station, TrackReaction
from tests.radio_support import FakeSpotify, canonical_with_alias, engine_response, sp_track

ENGINE = 'recommender.services.client.fetch_identity_recommendations'
BASE = '/api/v1/radio/'


def seed(spotify_id='seed-1', kind='track', title='Seed Song', artwork='https://img.test/seed.jpg'):
    return {'kind': kind, 'spotifyId': spotify_id, 'title': title, 'subtitle': 'Seed Artist', 'artworkUrl': artwork}


class RadioAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user(username='radio-owner', email='radio@example.test', password='radio-pass-123')
        self.other = User.objects.create_user(username='radio-other', email='other-radio@example.test')
        self.token = Token.objects.get_or_create(user=self.user)[0].key
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        self.fake = FakeSpotify()
        patcher = mock.patch('radio.services.spotify.get_client', return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        engine = mock.patch(ENGINE, return_value={'items': []})
        self.engine = engine.start()
        self.addCleanup(engine.stop)

    def create_station(self, **payload):
        payload.setdefault('seeds', [seed()])
        response = self.client.post(f'{BASE}stations/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def stations(self):
        return self.client.get(f'{BASE}stations/').data['stations']

    def personal(self):
        return next(station for station in self.stations() if station['kind'] == 'personal')


class RadioAuthTests(RadioAPITestCase):
    def test_every_endpoint_requires_authentication(self):
        self.client.credentials()
        station_id = uuid.uuid4()
        calls = [
            ('get', f'{BASE}stations/'), ('post', f'{BASE}stations/'), ('patch', f'{BASE}stations/{station_id}/'),
            ('delete', f'{BASE}stations/{station_id}/'), ('post', f'{BASE}stations/{station_id}/exclusions/'),
            ('delete', f'{BASE}exclusions/{station_id}/'), ('put', f'{BASE}reactions/'),
            ('post', f'{BASE}stations/{station_id}/next'), ('post', f'{BASE}play'), ('post', f'{BASE}events/'),
            ('get', f'{BASE}crate/'), ('get', f'{BASE}session/summary'),
        ]
        for method, url in calls:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 401)

    def test_token_and_bearer_headers_both_work(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        self.assertEqual(self.client.get(f'{BASE}stations/').status_code, 200)

    def test_user_isolation(self):
        mine = self.create_station()
        other_station = Station.objects.create(user=self.other, name='Theirs', frequency=99.1)
        self.assertNotIn(str(other_station.id), [station['id'] for station in self.stations()])
        for method, url in [('get', f'{BASE}stations/{other_station.id}/'), ('patch', f'{BASE}stations/{other_station.id}/'),
                            ('delete', f'{BASE}stations/{other_station.id}/'),
                            ('post', f'{BASE}stations/{other_station.id}/next')]:
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 404)
        theirs = Exclusion.objects.create(user=self.other, scope='everywhere', kind='artist', value='x')
        self.assertEqual(self.client.delete(f'{BASE}exclusions/{theirs.id}/').status_code, 404)
        self.assertEqual(self.client.put(f'{BASE}reactions/', {'spotifyTrackId': 't', 'stationId': str(other_station.id),
                                                               'reactions': ['🔥']}, format='json').status_code, 404)
        self.assertEqual(self.client.post(f'{BASE}events/', {'spotifyTrackId': 't', 'event': 'play',
                                                             'stationId': str(other_station.id)}, format='json').status_code, 404)
        self.assertTrue(Station.objects.filter(id=mine['id']).exists())


class StationTests(RadioAPITestCase):
    def test_first_listing_creates_personal_station_once(self):
        stations = self.stations()
        self.assertEqual(len(stations), 1)
        personal = stations[0]
        self.assertEqual((personal['name'], personal['kind'], personal['frequency'], personal['learning']),
                         ('My Station', 'personal', 88.7, True))
        self.assertEqual(set(personal), {'id', 'name', 'kind', 'frequency', 'seeds', 'thumbnails', 'feelings', 'learning',
                                         'exclusions', 'createdAt'})
        self.assertEqual(len(self.stations()), 1)
        self.assertEqual(Station.objects.filter(user=self.user, kind='personal').count(), 1)

    def test_create_station_defaults(self):
        station = self.create_station(seeds=[seed(), seed('seed-2', title='Two', artwork=None)], feelings=['🌙', ' 🌙 '])
        self.assertEqual(station['name'], 'Seed Song Radio')
        self.assertEqual(station['kind'], 'custom')
        self.assertEqual(station['frequency'], 107.9)
        self.assertEqual(station['feelings'], ['🌙'])
        self.assertEqual(station['thumbnails'], ['https://img.test/seed.jpg'])
        self.assertEqual(station['seeds'][1]['artworkUrl'], None)
        second = self.create_station(seeds=[], feelings=['🌧️', 'slow sunday'])
        self.assertEqual(second['name'], '🌧️ slow sunday Radio')
        self.assertEqual(second['frequency'], 105.7)
        named = self.create_station(name='  Kitchen  ')
        self.assertEqual(named['name'], 'Kitchen')
        self.assertEqual([s['frequency'] for s in self.stations()], [88.7, 103.5, 105.7, 107.9])

    def test_create_validation(self):
        for payload in ({}, {'seeds': [], 'feelings': []}, {'seeds': [{'kind': 'playlist', 'spotifyId': 'x', 'title': 'x'}]},
                        {'feelings': ['x' * 41]}, {'seeds': [{'kind': 'track', 'title': 'missing id'}]}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(f'{BASE}stations/', payload, format='json').status_code, 400)

    def test_patch_snaps_and_spaces_frequency(self):
        station = self.create_station()
        url = f"{BASE}stations/{station['id']}/"
        self.assertEqual(self.client.patch(url, {'frequency': 95.0}, format='json').data['frequency'], 95.1)
        self.assertEqual(self.client.patch(url, {'frequency': 89.5}, format='json').data['frequency'], 90.9)
        self.assertEqual(self.client.patch(url, {'frequency': 150}, format='json').data['frequency'], 107.9)
        updated = self.client.patch(url, {'name': 'Renamed', 'learning': False, 'feelings': ['☕'],
                                          'seeds': [seed('new', kind='artist', title='New Artist')]}, format='json').data
        self.assertEqual((updated['name'], updated['learning'], updated['feelings']), ('Renamed', False, ['☕']))
        self.assertEqual(updated['seeds'][0]['kind'], 'artist')
        self.assertEqual(self.client.patch(url, {'name': '  '}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'frequency': 'abc'}, format='json').status_code, 400)

    def test_delete(self):
        station = self.create_station()
        self.assertEqual(self.client.delete(f"{BASE}stations/{station['id']}/").status_code, 204)
        self.assertEqual(self.client.delete(f"{BASE}stations/{self.personal()['id']}/").status_code, 400)
        self.assertEqual([s['kind'] for s in self.stations()], ['personal'])

    def test_personal_thumbnails_come_from_cached_learned_tracks(self):
        self.fake.add(sp_track('loved', album_id='loved-album'))
        TrackReaction.objects.create(user=self.user, spotify_track_id='loved', reactions=['🔥'])
        self.assertEqual(self.personal()['thumbnails'], [])  # cache-only: nothing fetched yet
        self.client.get(f'{BASE}crate/?kind=tracks')  # hydrates
        self.assertEqual(self.personal()['thumbnails'], ['https://img.test/loved-album.jpg'])


class ExclusionTests(RadioAPITestCase):
    def test_create_scoped_and_everywhere_exclusions(self):
        first, second = self.create_station(), self.create_station()
        url = f"{BASE}stations/{first['id']}/exclusions/"
        scoped = self.client.post(url, {'scope': 'station', 'kind': 'track', 'value': 't1', 'label': 'Song'}, format='json')
        self.assertEqual(scoped.status_code, 201)
        self.assertEqual(set(scoped.data), {'id', 'scope', 'kind', 'value', 'label'})
        everywhere = self.client.post(url, {'scope': 'everywhere', 'kind': 'artist', 'value': 'ar1', 'label': 'Ana'}, format='json')
        self.assertIsNone(Exclusion.objects.get(id=everywhere.data['id']).station_id)
        again = self.client.post(url, {'scope': 'everywhere', 'kind': 'artist', 'value': 'ar1'}, format='json')
        self.assertEqual((again.status_code, again.data['id']), (200, everywhere.data['id']))
        by_id = {s['id']: s for s in self.stations()}
        self.assertEqual({e['value'] for e in by_id[first['id']]['exclusions']}, {'t1', 'ar1'})
        self.assertEqual({e['value'] for e in by_id[second['id']]['exclusions']}, {'ar1'})
        self.assertEqual(self.client.post(url, {'scope': 'galaxy', 'kind': 'track', 'value': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(f"{BASE}exclusions/{scoped.data['id']}/").status_code, 204)
        self.assertEqual(self.client.delete(f"{BASE}exclusions/{scoped.data['id']}/").status_code, 404)

    def test_exclusions_are_honoured_by_next(self):
        station = self.create_station()
        items = [canonical_with_alias(name) for name in ('t-bad', 't-good')]
        self.fake.add(sp_track('t-bad', artist_id='bad'), sp_track('t-good', artist_id='good'))
        self.engine.return_value = engine_response(*items)
        self.client.post(f"{BASE}stations/{station['id']}/exclusions/", {'scope': 'everywhere', 'kind': 'artist', 'value': 'bad'},
                         format='json')
        response = self.client.post(f"{BASE}stations/{station['id']}/next", {'count': 2}, format='json')
        self.assertEqual([t['spotifyId'] for t in response.data['tracks']], ['t-good'])


class ReactionTests(RadioAPITestCase):
    def test_upsert_dedupe_and_clear(self):
        payload = {'spotifyTrackId': 'track-1', 'reactions': ['🔥', '🔥', ' so good ', 'SO GOOD']}
        response = self.client.put(f'{BASE}reactions/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'reactions': ['🔥', 'so good'], 'suggestion': None})
        self.client.put(f'{BASE}reactions/', {'spotifyTrackId': 'track-1', 'reactions': ['🌙']}, format='json')
        self.assertEqual(TrackReaction.objects.get(user=self.user, spotify_track_id='track-1').reactions, ['🌙'])
        self.client.put(f'{BASE}reactions/', {'spotifyTrackId': 'track-1', 'reactions': []}, format='json')
        self.assertFalse(TrackReaction.objects.filter(user=self.user).exists())

    def test_validation(self):
        for reactions in (['x' * 41], 'not-a-list', [['nested']]):
            with self.subTest(reactions=reactions):
                response = self.client.put(f'{BASE}reactions/', {'spotifyTrackId': 't', 'reactions': reactions}, format='json')
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.put(f'{BASE}reactions/', {'reactions': ['🔥']}, format='json').status_code, 400)

    def test_suggestion_when_another_station_fits_better(self):
        morning = self.create_station(name='Morning', feelings=['☕'])
        night = self.create_station(name='Night', seeds=[], feelings=['🌙', 'rainy day'])
        response = self.client.put(f'{BASE}reactions/', {'spotifyTrackId': 't', 'stationId': morning['id'],
                                                         'reactions': ['🌙', '🌧️']}, format='json')
        self.assertEqual(response.data['suggestion'], {'stationId': night['id'], 'name': 'Night', 'matched': ['🌙', '🌧️']})
        self.assertEqual(str(TrackReaction.objects.get(spotify_track_id='t').station_id), morning['id'])
        tie = self.client.put(f'{BASE}reactions/', {'spotifyTrackId': 't', 'stationId': night['id'], 'reactions': ['🌙']},
                              format='json')
        self.assertIsNone(tie.data['suggestion'])


class NextTests(RadioAPITestCase):
    def test_next_returns_tracks_and_source(self):
        station = self.create_station()
        items = [canonical_with_alias(f'ml-{idx}') for idx in range(4)]
        self.fake.add(*[sp_track(f'ml-{idx}', artist_id=f'a{idx}') for idx in range(4)])
        self.engine.return_value = engine_response(*items)
        ListeningEvent.objects.create(user=self.user, spotify_track_id='ml-0', event='complete')
        response = self.client.post(f"{BASE}stations/{station['id']}/next", {'recentTrackIds': ['ml-1']}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['source'], 'mlcore')
        self.assertEqual([t['spotifyId'] for t in response.data['tracks']], ['ml-2', 'ml-3'])
        track = response.data['tracks'][0]
        self.assertEqual(set(track), {'spotifyId', 'uri', 'title', 'artist', 'artistId', 'artistIds', 'artistNames',
                                      'album', 'albumId', 'artworkUrl',
                                      'durationMs'})
        self.assertEqual(self.client.post(f"{BASE}stations/{station['id']}/next/", {}, format='json').status_code, 200)

    def test_count_validation(self):
        station = self.create_station()
        for count in (0, 11, 'x'):
            with self.subTest(count=count):
                response = self.client.post(f"{BASE}stations/{station['id']}/next", {'count': count}, format='json')
                self.assertEqual(response.status_code, 400)

    def test_search_fallback_when_engine_down(self):
        station = self.create_station(seeds=[], feelings=['💃'])
        self.engine.side_effect = ConnectionError('engine down')
        self.fake.search_results['dance'] = [sp_track(f'd{idx}', artist_id=f'd{idx}') for idx in range(5)]
        response = self.client.post(f"{BASE}stations/{station['id']}/next", {'count': 3}, format='json')
        self.assertEqual(response.data['source'], 'search')
        self.assertEqual(len(response.data['tracks']), 3)

    def test_empty_result_is_not_an_error(self):
        station = self.create_station(seeds=[], feelings=['nothing matches'])
        response = self.client.post(f"{BASE}stations/{station['id']}/next", {}, format='json')
        self.assertEqual((response.status_code, response.data['tracks']), (200, []))


class PlayTests(RadioAPITestCase):
    def setUp(self):
        super().setUp()
        UserSocialAuth.objects.create(user=self.user, provider='spotify', uid='spotify-user', extra_data={
            'access_token': 'token', 'refresh_token': 'refresh', 'expires_at': timezone.now().timestamp() + 3600})
        self.station = self.create_station()
        item = canonical_with_alias('next-1')
        self.fake.add(sp_track('next-1'))
        self.engine.return_value = engine_response(item)
        spotify_patch = mock.patch('catalog.services.playback.spotipy.Spotify')
        self.spotipy = spotify_patch.start().return_value
        self.addCleanup(spotify_patch.stop)
        self.spotipy.current_playback.return_value = {'is_playing': True, 'progress_ms': 0, 'item': None, 'device': None}

    def test_play_now_starts_track_and_records_play(self):
        response = self.client.post(f'{BASE}play', {'stationId': self.station['id'], 'mode': 'now', 'deviceId': 'dev-1'},
                                    format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['track']['spotifyId'], 'next-1')
        self.assertTrue(response.data['state']['is_playing'])
        self.spotipy.start_playback.assert_called_once_with(device_id='dev-1', uris=['spotify:track:next-1'])
        self.assertTrue(ListeningEvent.objects.filter(user=self.user, event='play', spotify_track_id='next-1').exists())

    def test_queue_adds_to_spotify_queue_without_interrupting(self):
        response = self.client.post(f'{BASE}play/', {'stationId': self.station['id'], 'mode': 'queue'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.spotipy.add_to_queue.assert_called_once_with('spotify:track:next-1')
        self.spotipy.start_playback.assert_not_called()
        self.assertFalse(ListeningEvent.objects.filter(event='play').exists())
        # The queued track is remembered so the next pick moves on.
        self.assertEqual(self.client.post(f"{BASE}stations/{self.station['id']}/next", {}, format='json').data['tracks'], [])

    def test_queue_targets_device(self):
        self.client.post(f'{BASE}play', {'stationId': self.station['id'], 'mode': 'queue', 'deviceId': 'dev-9'}, format='json')
        self.spotipy.add_to_queue.assert_called_once_with('spotify:track:next-1', device_id='dev-9')
        self.assertTrue(ListeningEvent.objects.filter(event='queued', spotify_track_id='next-1').exists())

    def test_provider_not_linked(self):
        UserSocialAuth.objects.filter(user=self.user).delete()
        response = self.client.post(f'{BASE}play', {'stationId': self.station['id'], 'mode': 'now'}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (400, 'playback_provider_not_linked'))

    def test_provider_failure_is_bad_gateway(self):
        self.spotipy.add_to_queue.side_effect = SpotifyException(403, 1, 'Player command failed: Premium required')
        response = self.client.post(f'{BASE}play', {'stationId': self.station['id'], 'mode': 'queue'}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (502, 'playback_provider_failure'))
        self.assertFalse(ListeningEvent.objects.exists())

    def test_nothing_to_play(self):
        self.engine.return_value = {'items': []}
        ListeningEvent.objects.create(user=self.user, spotify_track_id='next-1', event='complete')
        self.fake.db.clear()
        response = self.client.post(f'{BASE}play', {'stationId': self.station['id'], 'mode': 'now'}, format='json')
        self.assertEqual(response.status_code, 409)

    def test_validation(self):
        self.assertEqual(self.client.post(f'{BASE}play', {'stationId': self.station['id'], 'mode': 'later'},
                                          format='json').status_code, 400)
        self.assertEqual(self.client.post(f'{BASE}play', {'stationId': str(uuid.uuid4()), 'mode': 'now'},
                                          format='json').status_code, 404)


class EventTests(RadioAPITestCase):
    def test_records_event(self):
        station = self.create_station()
        response = self.client.post(f'{BASE}events/', {'stationId': station['id'], 'spotifyTrackId': 't1', 'event': 'skip',
                                                       'positionMs': 1200, 'source': 'radio'}, format='json')
        self.assertEqual(response.status_code, 204)
        event = ListeningEvent.objects.get(user=self.user)
        self.assertEqual((event.event, event.position_ms, event.source, str(event.station_id)), ('skip', 1200, 'radio', station['id']))
        self.assertEqual(self.client.post(f'{BASE}events/', {'spotifyTrackId': 't1', 'event': 'queued'},
                                          format='json').status_code, 400)
        self.assertEqual(self.client.post(f'{BASE}events/', {'spotifyTrackId': 't1', 'event': 'play', 'positionMs': -1},
                                          format='json').status_code, 400)

    def test_keep_out_events_become_exclusions(self):
        station = self.create_station()
        self.fake.add(sp_track('t2', artist_id='ar-never', artist_name='Never'))
        self.client.post(f'{BASE}events/', {'stationId': station['id'], 'spotifyTrackId': 't1', 'event': 'not_on_station'},
                         format='json')
        self.client.post(f'{BASE}events/', {'spotifyTrackId': 't2', 'event': 'never_artist'}, format='json')
        self.client.post(f'{BASE}events/', {'spotifyTrackId': 't3', 'event': 'never_artist', 'artistId': 'ar-given'}, format='json')
        rows = {(e.scope, e.kind, e.value, e.label, str(e.station_id) if e.station_id else None) for e in Exclusion.objects.all()}
        self.assertEqual(rows, {('station', 'track', 't1', '', station['id']), ('everywhere', 'artist', 'ar-never', 'Never', None),
                                ('everywhere', 'artist', 'ar-given', '', None)})

    def test_positive_events_feed_personal_station(self):
        personal = self.personal()
        self.client.post(f'{BASE}events/', {'spotifyTrackId': 'loved-1', 'event': 'save'}, format='json')
        self.client.post(f"{BASE}stations/{personal['id']}/next", {}, format='json')
        seeds = [item['source_id'] for item in self.engine.call_args_list[0].args[1]['seed_items']]
        self.assertEqual(seeds, ['loved-1'])


class CrateTests(RadioAPITestCase):
    def test_search_crate(self):
        self.fake.search_results[('lateralus', 'track')] = [sp_track('s1')]
        self.fake.search_results[('lateralus', 'artist')] = [{'id': 'ar', 'name': 'TOOL', 'genres': ['prog'],
                                                              'images': [{'url': 'https://img.test/tool.jpg'}]}]
        self.fake.search_results[('lateralus', 'album')] = [{'id': 'al', 'name': 'Lateralus', 'artists': [{'name': 'TOOL'}],
                                                             'images': []}]
        tracks = self.client.get(f'{BASE}crate/', {'kind': 'tracks', 'q': 'lateralus'}).data['items']
        self.assertEqual(set(tracks[0]), {'id', 'kind', 'spotifyId', 'title', 'subtitle', 'artworkUrl', 'track'})
        self.assertEqual((tracks[0]['kind'], tracks[0]['track']['spotifyId']), ('track', 's1'))
        artists = self.client.get(f'{BASE}crate/', {'kind': 'artists', 'q': 'lateralus'}).data['items']
        self.assertEqual(artists[0], {'id': 'artist:ar', 'kind': 'artist', 'spotifyId': 'ar', 'title': 'TOOL', 'subtitle': 'prog',
                                      'artworkUrl': 'https://img.test/tool.jpg'})
        albums = self.client.get(f'{BASE}crate/', {'kind': 'albums', 'q': 'lateralus'}).data['items']
        self.assertEqual((albums[0]['subtitle'], albums[0]['artworkUrl']), ('TOOL', None))
        self.assertEqual(self.client.get(f'{BASE}crate/', {'kind': 'playlists'}).status_code, 400)

    def test_personal_crate_orders_seeds_loved_then_mlcore(self):
        self.create_station(seeds=[seed('seed-1'), seed('ar-seed', kind='artist', title='Seed Artist')])
        self.fake.add(sp_track('seed-1', artist_id='a1', album_id='al1'), sp_track('loved', artist_id='a2', album_id='al2'),
                      sp_track('pick', artist_id='a3', album_id='al3'))
        TrackReaction.objects.create(user=self.user, spotify_track_id='loved', reactions=['❤️'])
        self.engine.return_value = engine_response(canonical_with_alias('pick'))
        tracks = self.client.get(f'{BASE}crate/').data['items']
        self.assertEqual([item['spotifyId'] for item in tracks], ['seed-1', 'loved', 'pick'])
        artists = self.client.get(f'{BASE}crate/', {'kind': 'artists'}).data['items']
        self.assertEqual([item['spotifyId'] for item in artists], ['ar-seed', 'a1', 'a2', 'a3'])
        albums = self.client.get(f'{BASE}crate/', {'kind': 'albums'}).data['items']
        self.assertEqual([item['spotifyId'] for item in albums], ['al1', 'al2', 'al3'])

    def test_stubbed_spotify_crate_search(self):
        with mock.patch('radio.services.spotify.get_client', wraps=None) as get_client:
            from radio.services.spotify import StubSpotify
            get_client.return_value = StubSpotify()
            items = self.client.get(f'{BASE}crate/', {'kind': 'tracks', 'q': 'anything'}).data['items']
        self.assertTrue(items)


class SessionSummaryTests(RadioAPITestCase):
    def event(self, track_id, event, minutes_ago):
        row = ListeningEvent.objects.create(user=self.user, spotify_track_id=track_id, event=event)
        ListeningEvent.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))

    def test_empty_summary(self):
        self.assertEqual(self.client.get(f'{BASE}session/summary').data,
                         {'startedAt': None, 'songCount': 0, 'reactions': [], 'tracks': []})

    def test_summary_covers_current_session_only(self):
        self.fake.add(sp_track('a'), sp_track('b'), sp_track('old'))
        self.event('old', 'play', 200)
        self.event('a', 'play', 40)
        self.event('a', 'complete', 36)
        self.event('b', 'play', 20)
        self.event('queued-only', 'queued', 1)
        TrackReaction.objects.create(user=self.user, spotify_track_id='a', reactions=['🔥', '🌙'])
        TrackReaction.objects.create(user=self.user, spotify_track_id='b', reactions=['🌙'])
        TrackReaction.objects.create(user=self.user, spotify_track_id='old', reactions=['🥱'])
        data = self.client.get(f'{BASE}session/summary/').data
        self.assertEqual(data['songCount'], 2)
        self.assertEqual([track['spotifyId'] for track in data['tracks']], ['a', 'b'])
        self.assertEqual(data['reactions'], ['🔥', '🌙'])
        self.assertIsNotNone(data['startedAt'])


class ReviewFollowUpTests(RadioAPITestCase):
    def test_patch_accepts_raw_doubles_and_snaps(self):
        station = self.create_station()
        url = f"{BASE}stations/{station['id']}/"
        for raw, expected in ((95.27384, 95.3), (95.29999999999999, 95.3), (100.0000001, 100.1), ('99.4', 99.5)):
            with self.subTest(raw=raw):
                response = self.client.patch(url, {'frequency': raw}, format='json')
                self.assertEqual((response.status_code, response.data['frequency']), (200, expected))
        for bad in ('NaN', 'Infinity', -5, 5000):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.patch(url, {'frequency': bad}, format='json').status_code, 400)

    def test_station_writes_take_the_dial_lock(self):
        from radio import views

        with mock.patch.object(views, 'lock_dial', wraps=views.lock_dial) as lock:
            station = self.create_station()
            self.client.patch(f"{BASE}stations/{station['id']}/", {'frequency': 99.1}, format='json')
        self.assertEqual(lock.call_count, 2)

    def test_duplicate_exclusions_collapse_to_one_row(self):
        from django.db import IntegrityError, transaction

        station = self.create_station()
        Exclusion.objects.create(user=self.user, scope='everywhere', kind='artist', value='ar', label='Ar')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exclusion.objects.create(user=self.user, scope='everywhere', kind='artist', value='ar')
        scoped = Station.objects.get(id=station['id'])
        Exclusion.objects.create(user=self.user, station=scoped, scope='station', kind='track', value='t')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exclusion.objects.create(user=self.user, station=scoped, scope='station', kind='track', value='t')
        # Another user / another station may hold the same rule.
        Exclusion.objects.create(user=self.other, scope='everywhere', kind='artist', value='ar')

    def test_exclusion_race_returns_existing_row(self):
        from radio import views

        station = Station.objects.get(id=self.create_station()['id'])
        existing = Exclusion.objects.create(user=self.user, scope='everywhere', kind='track', value='t9')
        real_filter = Exclusion.objects.filter
        with mock.patch.object(Exclusion.objects, 'filter',
                               side_effect=lambda **kw: real_filter(pk=None) if 'value' in kw else real_filter(**kw)):
            exclusion, created = views.add_exclusion(self.user, station, 'everywhere', 'track', 't9')
        self.assertEqual((exclusion.pk, created), (existing.pk, False))
        response = self.client.post(f"{BASE}stations/{station.id}/exclusions/",
                                    {'scope': 'everywhere', 'kind': 'track', 'value': 't9'}, format='json')
        self.assertEqual((response.status_code, response.data['id']), (200, str(existing.pk)))

    def test_artist_exclusion_labels_are_resolved(self):
        station = self.create_station()
        self.fake.artists['ar-x'] = 'Resolved Name'
        response = self.client.post(f"{BASE}stations/{station['id']}/exclusions/",
                                    {'scope': 'everywhere', 'kind': 'artist', 'value': 'ar-x'}, format='json')
        self.assertEqual(response.data['label'], 'Resolved Name')
        self.fake.add(sp_track('duet', artist_id='lead', artist_name='Lead', featuring=[('feat', 'Feature')]))
        self.client.post(f'{BASE}events/', {'spotifyTrackId': 'duet', 'event': 'never_artist', 'artistId': 'feat'}, format='json')
        self.assertEqual(Exclusion.objects.get(value='feat').label, 'Feature')

    def test_featured_artist_and_evidence_tracks_respect_exclusions(self):
        station = self.create_station()
        items = [canonical_with_alias('duet'), canonical_with_alias('ev-only', evidence={'name': 'E', 'artists': ['Feature']}),
                 canonical_with_alias('fine')]
        self.fake.add(sp_track('duet', artist_id='lead', featuring=[('feat', 'Feature')]), sp_track('fine', artist_id='ok'))
        self.fake.artists['feat'] = 'Feature'
        self.engine.return_value = engine_response(*items)
        self.client.post(f"{BASE}stations/{station['id']}/exclusions/",
                         {'scope': 'everywhere', 'kind': 'artist', 'value': 'feat'}, format='json')
        response = self.client.post(f"{BASE}stations/{station['id']}/next", {'count': 3}, format='json')
        self.assertEqual([t['spotifyId'] for t in response.data['tracks']], ['fine'])

    def test_session_summary_counts_queued_tracks_the_client_reported(self):
        self.fake.add(sp_track('q1'), sp_track('q2'))
        for track_id, event, minutes in (('q1', 'queued', 12), ('q1', 'complete', 8), ('q2', 'queued', 4)):
            row = ListeningEvent.objects.create(user=self.user, spotify_track_id=track_id, event=event)
            ListeningEvent.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))
        data = self.client.get(f'{BASE}session/summary').data
        self.assertEqual((data['songCount'], [t['spotifyId'] for t in data['tracks']]), (1, ['q1']))

    def test_session_summary_queued_only_is_empty(self):
        ListeningEvent.objects.create(user=self.user, spotify_track_id='q1', event='queued')
        self.assertEqual(self.client.get(f'{BASE}session/summary').data['songCount'], 0)

    def test_session_summary_after_gap_is_empty(self):
        row = ListeningEvent.objects.create(user=self.user, spotify_track_id='a', event='complete')
        ListeningEvent.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(minutes=45))
        self.assertIsNone(self.client.get(f'{BASE}session/summary').data['startedAt'])

    def test_session_summary_survives_spotify_outage(self):
        ListeningEvent.objects.create(user=self.user, spotify_track_id='down-1', event='play')
        self.fake.fail_batch = TimeoutError('timed out')
        data = self.client.get(f'{BASE}session/summary').data
        self.assertEqual((data['songCount'], data['tracks'][0]['spotifyId'], data['tracks'][0]['title']), (1, 'down-1', ''))

    def test_radio_uses_its_own_throttle_scope(self):
        from radio.views import RadioAPIView

        self.assertEqual([throttle.scope for throttle in RadioAPIView.throttle_classes], ['radio_user'])
