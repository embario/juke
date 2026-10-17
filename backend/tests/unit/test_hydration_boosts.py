import datetime
import uuid
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from catalog.models import Album, SearchHistory, SearchHistoryResource, Track
from mlcore.models import CanonicalItem, ListenBrainzSessionTrack, ProviderHydrationItem, ProviderHydrationRun
from mlcore.services.hydration_boosts import (
    LIBRARY_PRIORITY,
    PLAYBACK_PRIORITY,
    apply_referenced_boosts,
    boost_priority,
    collect_referenced_spotify_tracks,
    referenced_canonical_priorities,
)
from mlcore.services.provider_hydration import UNSCORED_PRIORITY, claim_hydration_item, rescore_pending_priorities
from radio.models import ListeningEvent, Station, TrackReaction

User = get_user_model()


class BoostPriorityTests(SimpleTestCase):
    def test_tiers_never_overlap_and_both_sit_ahead_of_the_corpus_scores(self):
        library = [boost_priority(LIBRARY_PRIORITY, users) for users in range(1, 40)]
        playback = [boost_priority(PLAYBACK_PRIORITY, users) for users in range(1, 40)]
        self.assertLess(max(library), min(playback))
        self.assertLess(max(playback), 1)
        self.assertEqual(library, sorted(library, reverse=True))
        self.assertEqual(boost_priority(PLAYBACK_PRIORITY, 0), PLAYBACK_PRIORITY)


class BoostFixtureMixin:
    def user(self, name):
        return User.objects.create_user(username=name, email=f'{name}@example.com', password='x')

    def track(self, spotify_id, mbid=None):
        album = Album.objects.create(
            name=f'Album {spotify_id}', spotify_id=f'al-{spotify_id}', total_tracks=1, release_date=datetime.date(2020, 1, 1),
        )
        return Track.objects.create(
            name=f'Track {spotify_id}', spotify_id=spotify_id, album=album, track_number=1, duration_ms=1000, mbid=mbid,
        )

    def queued(self, *, spotify_id=None, mbid=None, listens=0, status='pending'):
        """A queued hydration item. ``spotify_id`` links it through a catalog Track, ``mbid`` through its key."""
        track = self.track(spotify_id, mbid=mbid) if spotify_id else None
        key = f'recording_mbid:{mbid or uuid.uuid4()}'
        canonical = CanonicalItem.objects.create(
            id=uuid.uuid4(), item_type='recording_mbid', canonical_key=key, track=None if mbid else track,
        )
        now = timezone.now()
        for _ in range(listens):
            ListenBrainzSessionTrack.objects.create(
                session_key=uuid.uuid4().bytes * 2, canonical_item=canonical, first_played_at=now, last_played_at=now,
            )
        return ProviderHydrationItem.objects.create(
            canonical_item=canonical, provider='spotify', identifier_type='isrc',
            identifier=f'ISRC{uuid.uuid4().hex[:8]}'.upper(), status=status,
        )

    @staticmethod
    def event(user, spotify_id, kind):
        return ListeningEvent.objects.create(user=user, spotify_track_id=spotify_id, event=kind)


class CollectReferencesTests(BoostFixtureMixin, TestCase):
    def test_library_playback_seed_and_search_references_get_tiered_priorities(self):
        ann, bob = self.user('ann'), self.user('bob')
        self.event(ann, 'played-two-users', 'play')
        self.event(bob, 'played-two-users', 'complete')
        self.event(ann, 'saved-one-user', 'save')
        self.event(ann, 'skipped-only', 'skip')
        self.event(ann, 'queued-only', 'queued')
        self.event(ann, 'less-only', 'less')
        TrackReaction.objects.create(user=bob, spotify_track_id='reacted', reactions=['🔥'])
        TrackReaction.objects.create(user=bob, spotify_track_id='empty-reaction', reactions=[])
        Station.objects.create(
            user=ann, name='S', frequency='88.1', seeds=[{'kind': 'track', 'spotifyId': 'seeded'}, {'kind': 'artist', 'spotifyId': 'x'}],
        )
        clicked = self.track('clicked')
        history = SearchHistory.objects.create(user=bob, search_query='q')
        SearchHistoryResource.objects.create(
            search_history=history, resource_type='track', resource_id=clicked.pk, resource_name='n',
        )

        found = collect_referenced_spotify_tracks()

        self.assertEqual(found['played-two-users'], boost_priority(PLAYBACK_PRIORITY, 2))
        self.assertEqual(found['saved-one-user'], LIBRARY_PRIORITY)
        self.assertEqual(found['reacted'], LIBRARY_PRIORITY)
        self.assertEqual(found['seeded'], PLAYBACK_PRIORITY)
        self.assertEqual(found['clicked'], PLAYBACK_PRIORITY)
        for ignored in ('skipped-only', 'queued-only', 'less-only', 'empty-reaction', 'x'):
            self.assertNotIn(ignored, found)

    def test_a_track_both_saved_and_played_keeps_the_library_priority(self):
        ann = self.user('ann')
        self.event(ann, 'both', 'play')
        self.event(ann, 'both', 'save')
        self.assertEqual(collect_referenced_spotify_tracks()['both'], LIBRARY_PRIORITY)


class ResolveAndClaimTests(BoostFixtureMixin, TestCase):
    def test_references_resolve_through_the_track_link_or_the_recording_key(self):
        by_track = self.queued(spotify_id='by-track')
        mbid = uuid.uuid4()
        by_key = self.queued(spotify_id='by-key', mbid=mbid)
        self.queued(spotify_id='unreferenced')

        resolved = referenced_canonical_priorities({'by-track': -12, 'by-key': -25, 'unknown': -20})

        self.assertEqual(resolved, {by_track.canonical_item_id: -12, by_key.canonical_item_id: -25})

    def test_references_also_resolve_through_the_isrc_in_the_tracks_spotify_data(self):
        item = self.queued()
        item.identifier = 'USRC17607839'
        item.save()
        track = self.track('isrc-linked')
        track.spotify_data = {'external_ids': {'isrc': 'us-rc1-76-07839'}}
        track.save()

        self.assertEqual(
            referenced_canonical_priorities({'isrc-linked': PLAYBACK_PRIORITY}),
            {item.canonical_item_id: PLAYBACK_PRIORITY},
        )

    def test_library_items_claim_before_playback_items_before_corpus_popular_before_the_rest(self):
        ann = self.user('ann')
        popular = self.queued(listens=500)
        plain = self.queued()
        played = self.queued(spotify_id='played')
        saved = self.queued(spotify_id='saved')
        self.event(ann, 'played', 'play')
        self.event(ann, 'saved', 'save')

        rescore_pending_priorities(batch_size=50)  # corpus scores only
        self.assertLess(ProviderHydrationItem.objects.get(pk=popular.pk).priority, UNSCORED_PRIORITY)

        boosts = referenced_canonical_priorities()
        self.assertEqual(apply_referenced_boosts(boosts), 2)
        rescore_pending_priorities(batch_size=50, boosts=boosts)

        run = ProviderHydrationRun.objects.create(provider='spotify')
        claimed = [claim_hydration_item(run=run, worker_id='w').pk for _ in range(4)]
        self.assertEqual(claimed, [saved.pk, played.pk, popular.pk, plain.pk])

    def test_boost_touches_only_pending_rows_and_rescore_does_not_undo_it(self):
        ann = self.user('ann')
        running = self.queued(spotify_id='running', status='running')
        pending = self.queued(spotify_id='pending')
        self.event(ann, 'running', 'save')
        self.event(ann, 'pending', 'save')
        boosts = referenced_canonical_priorities()

        self.assertEqual(apply_referenced_boosts(boosts), 1)
        running.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual((running.priority, pending.priority), (UNSCORED_PRIORITY, LIBRARY_PRIORITY))

        rescore_pending_priorities(batch_size=10, boosts=boosts)
        pending.refresh_from_db()
        self.assertEqual(pending.priority, LIBRARY_PRIORITY)
        self.assertEqual(apply_referenced_boosts(boosts), 0, 'a second boost pass writes nothing')

        rescore_pending_priorities(batch_size=10)  # without the boost map the corpus score takes over again
        pending.refresh_from_db()
        self.assertEqual(pending.priority, UNSCORED_PRIORITY)


class BackfillBoostTests(BoostFixtureMixin, TestCase):
    def test_backfill_command_applies_boosts_first_and_can_skip_them(self):
        ann = self.user('ann')
        item = self.queued(spotify_id='saved')
        self.event(ann, 'saved', 'save')

        output = StringIO()
        call_command('rescore_hydration_priority', sleep_seconds=0, stdout=output, skip_boosts=True)
        item.refresh_from_db()
        self.assertEqual(item.priority, UNSCORED_PRIORITY)

        output = StringIO()
        call_command('rescore_hydration_priority', sleep_seconds=0, stdout=output)
        item.refresh_from_db()
        self.assertEqual(item.priority, LIBRARY_PRIORITY)
        self.assertIn('boosted_items=1 boosted_rows=1', output.getvalue())
