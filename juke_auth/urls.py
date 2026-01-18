from django.urls import include, path
from rest_framework import routers
from rest_framework.authtoken import views as authtoken_views
from juke_auth import views

router = routers.DefaultRouter()
router.register(r'users', views.JukeUserViewSet)
router.register(r'music-profiles', views.MusicProfileViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('accounts/', include('rest_registration.api.urls')),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('api-auth-token/', authtoken_views.obtain_auth_token),
    path('social-login/', views.SocialAuth.as_view(), name='social_login'),
    path('social-auth/', include('social_django.urls')),

]
