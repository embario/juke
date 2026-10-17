"""Characterization tests for docs/radio-exhaustion-and-relevance-findings.md (round 3, PR S).

These pin what radio does TODAY so the findings stay reproducible; they change no behavior and need
no database or network (MLCore and Spotify are replaced with deterministic fakes). A fix task that
changes one of these behaviors updates the matching test together with the code.
"""
import contextlib
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from radio.services import feelings as feeling_rules
from radio.services import recommend, signals

PAGE = 10  # spotify.SEARCH_LIMIT
SEED_ARTIST = 'artist-seed'
SEED_TRACK = 'seed-track'


def _track(track_id, artist_id, name=None):
    return {'spotifyId': track_id, 'uri': f'spotify:track:{track_id}', 'title': name or f'Song {track_id}', 'artist': artist_id,
            'artistId': artist_id, 'artistIds': [artist_id], 'artistNames': [artist_id], 'album': '', 'albumId': '',
            'artworkUrl': None, 'durationMs': 200000}


class _World:
    """A deterministic Spotify: ``top`` top tracks for the seed artist and ``pages`` search pages per query.

    MLCore is always empty, as on the deployed extra stack (the seeds do not resolve to canonical items).
    """

    def __init__(self, top=10, genres=None, search_queries_seen=None):
        self.top = [_track(f'top-{i}', SEED_ARTIST) for i in range(top)]
        self.genres = genres or {}
        self.queries = search_queries_seen if search_queries_seen is not None else []
        self.genre_lookups = []

    def search_tracks(self, query, limit=PAGE, offset=0):
        self.queries.append((query, offset))
        return [_track(f'{query}|{offset}|{i}', f'artist-{query}-{i}') for i in range(PAGE)]

    def artist_genres(self, artist_ids):
        self.genre_lookups.append(list(artist_ids))
        return {artist_id: self.genres[artist_id] for artist_id in artist_ids if artist_id in self.genres}

    def pick(self, recent_ids, feelings=(), count=1):
        """One ``next_tracks`` call with ``recent_ids`` excluded; returns the Recommendation."""
        ctx = recommend._Context(
            station=SimpleNamespace(pk='station', seeds=[{'kind': 'track', 'spotifyId': SEED_TRACK, 'title': 'Seed'}]),
            seed_track_ids=[SEED_TRACK], seed_artist_ids=[], feelings=list(feelings),
            flt=signals.ExclusionFilter.build([], recent_ids))
        seed_payload = {SEED_TRACK: _track(SEED_TRACK, SEED_ARTIST)}
        patches = {
            'get_tracks': lambda ids: {i: seed_payload[i] for i in ids if i in seed_payload},
            'cached_tracks': lambda ids: seed_payload,
            'artist_top_tracks': lambda artist_id: self.top if artist_id == SEED_ARTIST else [],
            'search_tracks': self.search_tracks,
            'artist_genres': self.artist_genres,
        }
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(recommend, 'build_context', return_value=ctx))
            stack.enter_context(mock.patch.object(recommend, 'mlcore_track_ids', return_value=[]))
            for name, fake in patches.items():
                stack.enter_context(mock.patch.object(recommend.spotify, name, side_effect=fake))
            return recommend._next_tracks(None, ctx.station, count, recent_ids)

    def play(self, picks, feelings=(), window=signals.RECENT_HISTORY_LIMIT):
        """Press Next ``picks`` times; every pick joins the history, of which only the last ``window`` count."""
        history, played = [], []
        for _ in range(picks):
            result = self.pick(list(reversed(history[-window:])), feelings)
            if not result.tracks:
                played.append(None)
                continue
            history.append(result.tracks[0]['spotifyId'])
            played.append(result.tracks[0])
        return played


class FeelingsOnSeededStations(SimpleTestCase):
    def test_feelings_do_not_choose_songs_while_seed_artist_tracks_remain(self):
        # F3: a seeded station fills from the seed artist's top tracks first; the sound search that
        # honours the feeling only runs once those are all in the history.
        world = _World(top=10)
        played = world.play(10, feelings=['🔥'])
        self.assertTrue(all(track['sources'][0] == 'artist:seed' for track in played))
        self.assertEqual(world.queries, [])  # Spotify search was never asked for "hype" music

    def test_after_the_top_tracks_the_search_ignores_the_seed(self):
        # F4: with feelings, the sound search uses only the feelings' genre filters; the seed's own
        # genres are consulted only when the station has no feelings.
        world = _World(top=10, genres={SEED_ARTIST: ['indie rock']})
        world.play(11, feelings=['🔥'])
        wanted = {f'genre:"{genre}"' if ' ' in genre else f'genre:{genre}' for genre in feeling_rules.PROFILES['hype'].genres}
        asked = {query for query, _ in world.queries}
        self.assertTrue(asked and asked <= wanted, asked)
        self.assertNotIn('genre:"indie rock"', asked)

    def test_seed_without_known_genres_falls_back_to_the_chill_profile(self):
        # F5: no feelings and no genres for the seed artist (Spotify often has none) → default "chill"
        # genres, whatever the seed sounds like.
        world = _World(top=3)
        world.play(4, feelings=[])
        asked = {query for query, _ in world.queries}
        self.assertIn('genre:chillhop', asked)

    def test_feeling_ranking_only_sees_two_candidates_when_one_song_is_asked(self):
        # F3b: /radio/play asks for one song, so the pool re-ranked by feeling affinity is 2 tracks, and
        # one-artist-per-pool means a single seed artist's top tracks are never re-ranked at all.
        one_artist = _World(top=10)
        one_artist.pick([], feelings=['🔥'])
        self.assertEqual(one_artist.genre_lookups, [])
        many_artists = _World(top=10)
        many_artists.top = [_track(f'top-{i}', f'f{i}') for i in range(10)]
        many_artists.pick([], feelings=['🔥'])
        looked_up = {artist_id for ids in many_artists.genre_lookups for artist_id in ids}
        self.assertEqual(looked_up, {'f0', 'f1'})


class ExhaustionAndRepeats(SimpleTestCase):
    def test_a_small_deterministic_pool_runs_dry_when_every_candidate_is_in_the_history(self):
        # F2: 3 top tracks and a search that is a single page of 10 per query → a 3 + 10 candidate pool
        # (the search is cached for an hour, so Spotify offers the same songs every time). The station's
        # own seed is the last resort, so it plays once more before the pool is empty.
        world = _World(top=3)
        with mock.patch.object(feeling_rules, 'search_queries', return_value=[('q', 'genre')]), \
                mock.patch.object(recommend.spotify, 'SEARCH_LIMIT', PAGE + 1):  # page 1 is "not full": no page 2
            played = world.play(15)
        self.assertEqual(played[13]['sources'], ['seed'])
        self.assertEqual([track is None for track in played], [False] * 14 + [True])

    def test_a_station_cycles_through_a_fixed_pool_of_about_fifty_songs(self):
        # F2b: only the last 50 distinct songs are excluded and every source is cached and ordered, so
        # a station with 10 top tracks and 4 "hype" genre queries (page 1 of each; page 2 is only fetched
        # once page 1 is all in the history) offers 51 distinct songs, then replays them in the same order.
        # Real Spotify genre searches overlap, so the real pool is smaller than this fake one.
        world = _World(top=10)
        ids = [track['spotifyId'] for track in world.play(54, feelings=['🔥'])]
        self.assertEqual(len(set(ids[:51])), 51)
        self.assertEqual(ids[51:54], ids[0:3])
