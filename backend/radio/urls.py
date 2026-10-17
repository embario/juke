from django.urls import path, re_path

from radio import views

UUID = r'(?P<{}>[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}})'

urlpatterns = [
    path('stations/', views.StationCollectionView.as_view(), name='radio-stations'),
    path('stations/<uuid:station_id>/', views.StationDetailView.as_view(), name='radio-station-detail'),
    path('stations/<uuid:station_id>/exclusions/', views.StationExclusionsView.as_view(), name='radio-station-exclusions'),
    re_path(r'^stations/' + UUID.format('station_id') + r'/next/?$', views.StationNextView.as_view(), name='radio-station-next'),
    path('exclusions/<uuid:exclusion_id>/', views.ExclusionDetailView.as_view(), name='radio-exclusion-detail'),
    path('reactions/', views.ReactionsView.as_view(), name='radio-reactions'),
    re_path(r'^play/?$', views.PlayView.as_view(), name='radio-play'),
    path('events/', views.EventsView.as_view(), name='radio-events'),
    path('crate/', views.CrateView.as_view(), name='radio-crate'),
    re_path(r'^session/summary/?$', views.SessionSummaryView.as_view(), name='radio-session-summary'),
]
