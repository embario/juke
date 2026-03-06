from django.contrib import admin, messages

from mlcore.models import CorpusManifest, ModelEvaluation, ModelPromotion
from mlcore.services.corpus import LicensePolicy
from mlcore.services.promotion import PromotionError, approve_promotion, reject_promotion


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


@admin.register(ModelEvaluation)
class ModelEvaluationAdmin(admin.ModelAdmin):
    list_display = ('candidate_label', 'metric_name', 'metric_value', 'short_hash', 'created_at')
    list_filter = ('candidate_label', 'metric_name')
    search_fields = ('candidate_label', 'dataset_hash')
    readonly_fields = ('candidate_label', 'metric_name', 'metric_value', 'dataset_hash',
                       'model_id', 'created_at')

    def short_hash(self, obj):
        return obj.dataset_hash[:12]
    short_hash.short_description = 'dataset'

    def has_add_permission(self, request):
        return False  # rows come from evaluate_recommenders only

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ModelPromotion)
class ModelPromotionAdmin(admin.ModelAdmin):
    list_display = ('candidate_label', 'baseline_label', 'status', 'short_hash',
                    'approved_by', 'approved_at', 'created_at')
    list_filter = ('status', 'candidate_label')
    search_fields = ('candidate_label', 'baseline_label', 'dataset_hash')
    # All fields read-only — status transitions go through the actions below,
    # which route through promotion.py so gates can't be bypassed by editing
    # status directly.
    readonly_fields = ('id', 'candidate_label', 'baseline_label', 'dataset_hash',
                       'status', 'gate_results', 'block_reason', 'approved_by',
                       'approved_at', 'created_at', 'model_id')
    actions = ['approve_selected', 'reject_selected']

    def short_hash(self, obj):
        return obj.dataset_hash[:12]
    short_hash.short_description = 'dataset'

    def has_add_permission(self, request):
        return False  # created via request_promotion / promote_recommender command

    @admin.action(description='Approve selected promotions (re-runs gate checks)')
    def approve_selected(self, request, queryset):
        ok, failed = 0, 0
        for promo in queryset:
            try:
                approve_promotion(promo, request.user)
                ok += 1
            except PromotionError as e:
                failed += 1
                self.message_user(request, f"{promo}: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"approved {ok} promotion(s)", level=messages.SUCCESS)

    @admin.action(description='Reject selected promotions')
    def reject_selected(self, request, queryset):
        ok, failed = 0, 0
        for promo in queryset:
            try:
                reject_promotion(promo, request.user, reason='rejected via admin action')
                ok += 1
            except PromotionError as e:
                failed += 1
                self.message_user(request, f"{promo}: {e}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"rejected {ok} promotion(s)", level=messages.SUCCESS)
