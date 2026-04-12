from django.test import TestCase, override_settings

from mlcore.models import CorpusManifest
from mlcore.services.corpus import SOURCE_CLASSIFICATION, LicensePolicy, PolicyDecision


def _mk(**overrides):
    defaults = dict(
        source='musicbrainz',
        track_path='/corpus/001.flac',
        license='CC-BY-4.0',
        allowed_envs='production',
        checksum='sha256:default',
    )
    defaults.update(overrides)
    return CorpusManifest.objects.create(**defaults)


@override_settings(JUKE_ALLOWED_LICENSES='production', JUKE_LICENSE_FAIL_CLOSED=True)
class LicensePolicyProductionModeTests(TestCase):

    def setUp(self):
        self.policy = LicensePolicy()

    # --- classify_source ---

    def test_classify_known_production_source(self):
        self.assertEqual(self.policy.classify_source('musicbrainz'), 'production_approved')

    def test_classify_listenbrainz_as_known_production_source(self):
        self.assertEqual(self.policy.classify_source('listenbrainz'), 'production_approved')

    def test_classify_unknown_source_fail_closed(self):
        self.assertEqual(self.policy.classify_source('random_dataset'), 'blocked')

    def test_classify_unknown_source_fail_open(self):
        open_policy = LicensePolicy(fail_closed=False)
        self.assertEqual(open_policy.classify_source('random_dataset'), 'research_only')

    # --- evaluate: compliant ---

    def test_compliant_musicbrainz_production_row(self):
        row = _mk()
        decision = self.policy.evaluate(row)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.classification, 'production_approved')
        self.assertEqual(decision.reason, 'compliant')

    def test_compliant_musicbrainz_both_row(self):
        row = _mk(allowed_envs='both', checksum='sha256:both')
        self.assertTrue(self.policy.evaluate(row).allowed)

    def test_compliant_listenbrainz_production_row(self):
        row = _mk(source='listenbrainz', checksum='sha256:lb')
        decision = self.policy.evaluate(row)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.classification, 'production_approved')

    # --- evaluate: reject branches ---

    def test_missing_license_rejected(self):
        row = _mk(license='', checksum='sha256:nolicense')
        decision = self.policy.evaluate(row)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, 'missing license metadata')
        self.assertEqual(decision.classification, 'blocked')

    def test_missing_allowed_envs_rejected(self):
        row = _mk(allowed_envs='', checksum='sha256:noenv')
        decision = self.policy.evaluate(row)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, 'missing allowed_envs')

    def test_unknown_source_rejected(self):
        row = _mk(source='unknown_dataset', checksum='sha256:unk')
        decision = self.policy.evaluate(row)
        self.assertFalse(decision.allowed)
        self.assertIn('not approved', decision.reason)
        self.assertEqual(decision.classification, 'blocked')

    def test_research_only_row_rejected_in_production_mode(self):
        row = _mk(allowed_envs='research', checksum='sha256:research')
        decision = self.policy.evaluate(row)
        self.assertFalse(decision.allowed)
        self.assertIn('excludes production', decision.reason)

    # --- eligible_queryset ---

    def test_eligible_queryset_production(self):
        good = _mk(checksum='sha256:good')
        _mk(source='unknown', checksum='sha256:bad-src')
        _mk(license='', checksum='sha256:no-lic')
        _mk(allowed_envs='research', checksum='sha256:research-only')

        eligible = self.policy.eligible_queryset()
        self.assertEqual(list(eligible), [good])

    def test_eligible_queryset_matches_evaluate(self):
        rows = [
            _mk(checksum='sha256:a'),
            _mk(source='unknown', checksum='sha256:b'),
            _mk(license='', checksum='sha256:c'),
            _mk(allowed_envs='research', checksum='sha256:d'),
            _mk(allowed_envs='both', checksum='sha256:e'),
        ]
        eligible_ids = set(self.policy.eligible_queryset().values_list('id', flat=True))
        for row in rows:
            decision = self.policy.evaluate(row)
            in_qs = row.id in eligible_ids
            self.assertEqual(decision.allowed, in_qs,
                f"mismatch for {row.source}/{row.allowed_envs}/{row.license!r}: "
                f"evaluate={decision.allowed}, queryset={in_qs}")

    # --- promotion guard ---

    def test_promotion_guard_all_clean(self):
        _mk(checksum='sha256:c1')
        _mk(checksum='sha256:c2', allowed_envs='both')
        ok, reason = self.policy.is_model_promotable(CorpusManifest.objects.all())
        self.assertTrue(ok)
        self.assertIn('production-compliant', reason)

    def test_promotion_guard_blocks_non_approved_source(self):
        _mk(checksum='sha256:ok')
        _mk(source='unknown', checksum='sha256:bad')
        with self.assertLogs('mlcore.services.corpus', level='WARNING') as cm:
            ok, reason = self.policy.is_model_promotable(CorpusManifest.objects.all())
        self.assertFalse(ok)
        self.assertIn('non-production_approved', reason)
        self.assertTrue(any('Promotion blocked' in msg for msg in cm.output))

    def test_promotion_guard_blocks_research_only_env(self):
        _mk(checksum='sha256:ok')
        _mk(allowed_envs='research', checksum='sha256:research')
        with self.assertLogs('mlcore.services.corpus', level='WARNING') as cm:
            ok, reason = self.policy.is_model_promotable(CorpusManifest.objects.all())
        self.assertFalse(ok)
        self.assertIn('research-only', reason)
        self.assertTrue(any('Promotion blocked' in msg for msg in cm.output))

    def test_policy_decision_is_frozen_dataclass(self):
        d = PolicyDecision(True, 'x', 'y')
        with self.assertRaises(Exception):
            d.allowed = False


@override_settings(JUKE_ALLOWED_LICENSES='research', JUKE_LICENSE_FAIL_CLOSED=True)
class LicensePolicyResearchModeTests(TestCase):

    def setUp(self):
        self.policy = LicensePolicy()

    def test_research_mode_allows_research_row(self):
        row = _mk(allowed_envs='research', checksum='sha256:r')
        self.assertTrue(self.policy.evaluate(row).allowed)

    def test_research_mode_rejects_production_only_row(self):
        row = _mk(allowed_envs='production', checksum='sha256:p')
        decision = self.policy.evaluate(row)
        self.assertFalse(decision.allowed)
        self.assertIn('excludes research', decision.reason)

    def test_research_mode_eligible_queryset(self):
        r1 = _mk(allowed_envs='research', checksum='sha256:r1')
        r2 = _mk(allowed_envs='both', checksum='sha256:r2')
        _mk(allowed_envs='production', checksum='sha256:p')  # excluded
        ids = set(self.policy.eligible_queryset().values_list('id', flat=True))
        self.assertIn(r1.id, ids)
        self.assertIn(r2.id, ids)
        self.assertEqual(len(ids), 2)


@override_settings(JUKE_ALLOWED_LICENSES='both', JUKE_LICENSE_FAIL_CLOSED=True)
class LicensePolicyBothModeTests(TestCase):

    def test_both_mode_admits_all_licensed_rows(self):
        policy = LicensePolicy()
        _mk(allowed_envs='production', checksum='sha256:p')
        _mk(allowed_envs='research', checksum='sha256:r')
        _mk(allowed_envs='both', checksum='sha256:b')
        self.assertEqual(policy.eligible_queryset().count(), 3)

    def test_both_mode_still_rejects_missing_license(self):
        policy = LicensePolicy()
        _mk(allowed_envs='production', checksum='sha256:p')
        _mk(license='', checksum='sha256:bad')
        self.assertEqual(policy.eligible_queryset().count(), 1)


class LicensePolicyExplicitArgsTests(TestCase):
    """Constructor overrides win over settings."""

    def test_explicit_args_override_settings(self):
        policy = LicensePolicy(allowed_licenses='research', fail_closed=False)
        self.assertEqual(policy.allowed_licenses, 'research')
        self.assertFalse(policy.fail_closed)
        self.assertEqual(policy.classify_source('unknown'), 'research_only')


class SourceRegistryExtensionTests(TestCase):
    """Dynamic extension of SOURCE_CLASSIFICATION is picked up."""

    def tearDown(self):
        SOURCE_CLASSIFICATION.pop('test_source', None)

    def test_new_approved_source(self):
        SOURCE_CLASSIFICATION['test_source'] = 'production_approved'
        policy = LicensePolicy(allowed_licenses='production')
        row = _mk(source='test_source', checksum='sha256:ext')
        self.assertTrue(policy.evaluate(row).allowed)
