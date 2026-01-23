from django.contrib import admin
from django.urls import include, path

from rest_framework import routers

from juke_auth.urls import router as auth_router
from catalog.urls import router as catalog_router

router = routers.DefaultRouter()
router.registry.extend(auth_router.registry)
router.registry.extend(catalog_router.registry)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('juke_auth.urls')),
    path('api/v1/social-auth/', include('social_django.urls', namespace='social')),
    path('api/v1/', include(router.urls)),
    path('api/v1/', include('recommender.urls')),
    path('api/v1/', include('powerhour.urls')),
    path('api/v1/tunetrivia/', include('tunetrivia.urls')),
]
