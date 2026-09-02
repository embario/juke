from django.urls import path

from journal import views


urlpatterns = [
    path('opening-question', views.JournalOpeningQuestionView.as_view(), name='journal-opening-question'),
    path('encrypted-records', views.JournalEncryptedChangesView.as_view(), name='journal-encrypted-changes'),
    path('encrypted-records/<uuid:record_id>', views.JournalEncryptedRecordView.as_view(), name='journal-encrypted-record'),
    path('chat', views.JournalChatView.as_view(), name='journal-chat'),
]
