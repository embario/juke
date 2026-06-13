from django.urls import path

from recommender.views import MLCoreRecommendationView, RecommendationView

urlpatterns = [
    path('recommendations/mlcore/', MLCoreRecommendationView.as_view(), name='mlcore-recommendations'),
    path('recommendations/', RecommendationView.as_view(), name='recommendations'),
]
