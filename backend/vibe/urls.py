from django.urls import path

from vibe import views


urlpatterns = [
    path('opening-question', views.VibeOpeningQuestionView.as_view(), name='vibe-opening-question'),
    path('encrypted-chat-records', views.VibeEncryptedChatChangesView.as_view(), name='vibe-encrypted-chat-changes'),
    path('encrypted-chat-records/<uuid:record_id>', views.VibeEncryptedChatRecordView.as_view(), name='vibe-encrypted-chat-record'),
    path('chat', views.VibeChatView.as_view(), name='vibe-chat'),
]

from vibe import memory_views  # noqa: E402

urlpatterns += [
    path('memories/', memory_views.MemoryCollectionView.as_view(), name='vibe-memories'),
    path('memories/classify/', memory_views.MemoryClassifyView.as_view(), name='vibe-memory-classify'),
    path('memories/<uuid:memory_id>/', memory_views.MemoryDetailView.as_view(), name='vibe-memory-detail'),
    path('memory-tags/', memory_views.MemoryTagsView.as_view(), name='vibe-memory-tags'),
    path('memory-recommendation-context/', memory_views.MemoryRecommendationContextView.as_view(),
         name='vibe-memory-recommendation-context'),
    path('memory-insights/', memory_views.MemoryInsightsView.as_view(), name='vibe-memory-insights'),
    path('memory-media/', memory_views.MemoryMediaUploadView.as_view(), name='vibe-memory-media'),
    path('memory-media/<uuid:media_id>/content/', memory_views.MemoryMediaContentView.as_view(), name='vibe-memory-media-content'),
]
