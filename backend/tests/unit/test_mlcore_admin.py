from django.contrib.admin.sites import AdminSite
from django.test import TestCase, override_settings

from mlcore.admin import CorpusManifestAdmin
from mlcore.models import CorpusManifest


@override_settings(JUKE_ALLOWED_LICENSES='production', JUKE_LICENSE_FAIL_CLOSED=True)
class CorpusManifestAdminTests(TestCase):

    def setUp(self):
        self.admin = CorpusManifestAdmin(CorpusManifest, AdminSite())

    def test_policy_status_allowed(self):
        row = CorpusManifest.objects.create(
            source='musicbrainz', track_path='/x.flac', license='CC-BY-4.0',
            allowed_envs='production', checksum='sha256:ok',
        )
        self.assertEqual(self.admin.policy_status(row), 'ALLOWED')

    def test_policy_status_blocked(self):
        row = CorpusManifest.objects.create(
            source='unknown', track_path='/y.flac', license='CC-BY-4.0',
            allowed_envs='production', checksum='sha256:bad',
        )
        self.assertEqual(self.admin.policy_status(row), 'BLOCKED')

    def test_policy_reason_compliant(self):
        row = CorpusManifest.objects.create(
            source='musicbrainz', track_path='/x.flac', license='CC-BY-4.0',
            allowed_envs='production', checksum='sha256:ok',
        )
        self.assertEqual(self.admin.policy_reason(row), 'compliant')

    def test_policy_reason_blocked_explains(self):
        row = CorpusManifest.objects.create(
            source='musicbrainz', track_path='/z.flac', license='',
            allowed_envs='production', checksum='sha256:nolicense',
        )
        self.assertIn('missing license', self.admin.policy_reason(row))

    def test_readonly_fields_include_policy_display(self):
        self.assertIn('policy_status', self.admin.readonly_fields)
        self.assertIn('policy_reason', self.admin.readonly_fields)
