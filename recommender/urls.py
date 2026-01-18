from django.urls import path

from recommender.views import RecommendationView

urlpatterns = [
    path('recommendations/', RecommendationView.as_view(), name='recommendations'),
]
