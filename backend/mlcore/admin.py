from django.contrib import admin

from mlcore.models import CorpusManifest
from mlcore.services.corpus import LicensePolicy


@admin.register(CorpusManifest)
class CorpusManifestAdmin(admin.ModelAdmin):
    list_display = ('source', 'track_path', 'license', 'allowed_envs', 'policy_status', 'ingested_at')
    list_filter = ('source', 'allowed_envs')
    search_fields = ('track_path', 'checksum', 'license')
    readonly_fields = ('id', 'ingested_at', 'policy_status', 'policy_reason')

    _policy = LicensePolicy()

    def policy_status(self, obj):
        return 'ALLOWED' if self._policy.evaluate(obj).allowed else 'BLOCKED'

    def policy_reason(self, obj):
        return self._policy.evaluate(obj).reason
