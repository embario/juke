from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'sessions', views.TuneTriviaSessionViewSet, basename='tunetrivia-session')
router.register(r'players', views.TuneTriviaPlayerViewSet, basename='tunetrivia-player')
router.register(r'rounds', views.TuneTriviaRoundViewSet, basename='tunetrivia-round')
router.register(r'leaderboard', views.TuneTriviaLeaderboardViewSet, basename='tunetrivia-leaderboard')

urlpatterns = router.urls
