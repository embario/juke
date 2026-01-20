from django.urls import include, path
from rest_framework import routers
from catalog import views

router = routers.DefaultRouter()
router.register(r'genres', views.GenreViewSet)
router.register(r'artists', views.ArtistViewSet)
router.register(r'albums', views.AlbumViewSet)
router.register(r'tracks', views.TrackViewSet)
router.register(r'playback', views.PlaybackViewSet, basename='playback')

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('', include(router.urls)),
]
