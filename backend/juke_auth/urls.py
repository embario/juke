from django.urls import include, path
from rest_framework import routers
from juke_auth import views

router = routers.DefaultRouter()
router.register(r'users', views.JukeUserViewSet)
router.register(r'music-profiles', views.MusicProfileViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('accounts/register/', views.JukeRegisterView.as_view(), name='juke_register'),
    path('accounts/resend-registration/', views.ResendRegistrationVerificationView.as_view(), name='resend_registration'),
    path('accounts/verify-registration/', views.JukeVerifyRegistrationView.as_view(), name='verify_registration'),
    path('accounts/', include('rest_registration.api.urls')),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('api-auth-token/', views.TokenLoginView.as_view(), name='api_token_login'),
    path('session/logout/', views.TokenLogoutView.as_view(), name='session_logout'),
    path('social-login/', views.SocialAuth.as_view(), name='social_login'),

]
