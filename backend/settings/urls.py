from django.contrib import admin
from django.urls import include, path

from rest_framework import routers

from juke_auth.urls import router as auth_router
from juke_auth import views as auth_views
from vibe import views as vibe_views
from journal import views as journal_views
from catalog.urls import router as catalog_router

router = routers.DefaultRouter()
router.registry.extend(auth_router.registry)
router.registry.extend(catalog_router.registry)


urlpatterns = [
    path('api/v1/health', vibe_views.HealthView.as_view(), name='api-health'),
    path('admin/', admin.site.urls),
    path('api/v1/auth/vibe/authorize', vibe_views.VibeAuthorizeView.as_view(), name='vibe-authorize'),
    path('api/v1/auth/vibe/exchange', vibe_views.VibeExchangeView.as_view(), name='vibe-exchange'),
    path('api/v1/auth/journal/authorize', journal_views.JournalAuthorizeView.as_view(), name='journal-authorize'),
    path('api/v1/auth/journal/exchange', journal_views.JournalExchangeView.as_view(), name='journal-exchange'),
    path('api/v1/auth/', include('juke_auth.urls')),
    path('api/v1/social-auth/login/spotify/', auth_views.spotify_login, name='spotify_login'),
    path('api/v1/social-auth/complete/spotify/', auth_views.spotify_complete, name='spotify_complete'),
    path('api/v1/social-auth/', include('social_django.urls', namespace='social')),
    path('api/v1/', include(router.urls)),
    path('api/v1/', include('recommender.urls')),
    path('api/v1/', include('powerhour.urls')),
    path('api/v1/tunetrivia/', include('tunetrivia.urls')),
    path('api/v1/vibe/', include('vibe.urls')),
    path('api/v1/journal/', include('journal.urls')),
]
