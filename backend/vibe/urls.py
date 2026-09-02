from django.urls import path

from vibe import views


urlpatterns = [
    path('opening-question', views.VibeOpeningQuestionView.as_view(), name='vibe-opening-question'),
    path('encrypted-chat-records', views.VibeEncryptedChatChangesView.as_view(), name='vibe-encrypted-chat-changes'),
    path('encrypted-chat-records/<uuid:record_id>', views.VibeEncryptedChatRecordView.as_view(), name='vibe-encrypted-chat-record'),
    path('chat', views.VibeChatView.as_view(), name='vibe-chat'),
]
