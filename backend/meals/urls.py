from django.urls import path, include
from rest_framework.routers import DefaultRouter
from meals.views import MealViewSet, MealSummaryView, MealTrendsView, QuickAddView

router = DefaultRouter()
router.register(r'meals', MealViewSet, basename='meal')

urlpatterns = [
    path('api/meals/summary/', MealSummaryView.as_view(), name='meal-summary'),
    path('api/meals/trends/', MealTrendsView.as_view(), name='meal-trends'),
    path('api/meals/quick-add/', QuickAddView.as_view(), name='meal-quick-add'),
    path('api/', include(router.urls)),
]
