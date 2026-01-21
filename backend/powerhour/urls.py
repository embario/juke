from rest_framework.routers import DefaultRouter

from .views import SessionViewSet

router = DefaultRouter()
router.register(r'powerhour/sessions', SessionViewSet, basename='powerhour-session')

urlpatterns = router.urls
