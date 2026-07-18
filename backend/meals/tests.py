from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from meals.models import Meal

class MealValidationTests(APITestCase):
    def setUp(self):
        self.url = reverse('meal-list')

    def test_create_valid_meal(self):
        data = {
            "name": "Paneer Tikka",
            "calories": 320,
            "protein_g": 24,
            "carbs_g": 12,
            "fat_g": 18,
            "tags": ["vegetarian", "high-protein"],
            "eaten_at": (timezone.now() - timedelta(hours=1)).isoformat()
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Meal.objects.count(), 1)
        self.assertEqual(Meal.objects.first().source, 'manual')

    def test_invalid_calories(self):
        data = {
            "name": "Heavy Meal",
            "calories": 6000,  # Max is 5000
            "protein_g": 20,
            "carbs_g": 20,
            "fat_g": 20,
            "tags": ["snack"],
            "eaten_at": timezone.now().isoformat()
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('calories', response.data)

    def test_invalid_tags(self):
        data = {
            "name": "Spicy Food",
            "calories": 300,
            "protein_g": 10,
            "carbs_g": 10,
            "fat_g": 10,
            "tags": ["junk-food"],  # Not in allowed tags
            "eaten_at": timezone.now().isoformat()
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('tags', response.data)

    def test_future_eaten_at(self):
        data = {
            "name": "Tomorrow Breakfast",
            "calories": 300,
            "protein_g": 10,
            "carbs_g": 10,
            "fat_g": 10,
            "tags": ["vegetarian"],
            "eaten_at": (timezone.now() + timedelta(days=1)).isoformat()
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('eaten_at', response.data)

    def test_duplicate_guard(self):
        eaten_time = timezone.now() - timedelta(hours=2)
        # Create first meal
        Meal.objects.create(
            name="Paneer Tikka",
            calories=320,
            protein_g=24,
            carbs_g=12,
            fat_g=18,
            tags=["vegetarian"],
            eaten_at=eaten_time
        )

        # Attempt to create duplicate (similar normalized name, within 30 min)
        data = {
            "name": "  paneer   TIKKA  ", # normalized is "paneer tikka"
            "calories": 350,
            "protein_g": 20,
            "carbs_g": 10,
            "fat_g": 15,
            "tags": ["vegetarian"],
            "eaten_at": (eaten_time + timedelta(minutes=15)).isoformat() # +15 min is within +/- 30 min
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Meal.objects.count(), 1)


class MealSummaryTests(APITestCase):
    def test_summary_calculation(self):
        date_str = "2026-06-12"
        # Setup meals
        Meal.objects.create(
            name="Oatmeal", calories=350, protein_g=12, carbs_g=60, fat_g=6,
            tags=["vegetarian"], eaten_at=timezone.make_aware(datetime.strptime(f"{date_str} 08:00:00", "%Y-%m-%d %H:%M:%S"))
        )
        Meal.objects.create(
            name="Salad", calories=320, protein_g=24, carbs_g=12, fat_g=18,
            tags=["vegetarian", "high-protein"], eaten_at=timezone.make_aware(datetime.strptime(f"{date_str} 13:30:00", "%Y-%m-%d %H:%M:%S"))
        )

        response = self.client.get(reverse('meal-summary'), {'date': date_str})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Validate totals
        self.assertEqual(response.data['total_calories'], 670)
        self.assertEqual(response.data['meal_count'], 2)
        self.assertEqual(response.data['macros']['protein_g'], 36)
        self.assertEqual(response.data['macros']['carbs_g'], 72)
        self.assertEqual(response.data['macros']['fat_g'], 24)
        
        # Vegetarian was logged twice, high-protein once. So top_tags is ["vegetarian"]
        self.assertEqual(response.data['top_tags'], ["vegetarian"])


class MealTrendsTests(APITestCase):
    def test_trends_gap_filling_and_query_limits(self):
        # Create meals on separate days with gaps
        base_time = timezone.now()
        day1 = base_time - timedelta(days=4)
        day2 = base_time - timedelta(days=2) # Gap on day3, day1, day0
        
        Meal.objects.create(
            name="Meal Day 4", calories=1500, protein_g=40, carbs_g=100, fat_g=40,
            tags=["high-protein"], eaten_at=day1
        )
        Meal.objects.create(
            name="Meal Day 2", calories=2500, protein_g=50, carbs_g=150, fat_g=50,
            tags=["high-protein"], eaten_at=day2
        )

        # Trigger trends endpoint with 5 days
        response = self.client.get(reverse('meal-trends'), {'days': 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        series = response.data['series']
        self.assertEqual(len(series), 5) # Enforces gap filling to N elements
        
        # Verify calories totals are distributed properly and gaps are zeroed
        date_map = {row['date']: row['calories'] for row in series}
        self.assertEqual(date_map[day1.strftime('%Y-%m-%d')], 1500)
        self.assertEqual(date_map[day2.strftime('%Y-%m-%d')], 2500)
        self.assertEqual(date_map[(base_time - timedelta(days=3)).strftime('%Y-%m-%d')], 0) # Gap filled

        # Average: (1500 + 2500) / 5 = 800
        self.assertEqual(response.data['avg_daily_kcal'], 800)
        # Best day should be Day 2 with 2500 kcal
        self.assertEqual(response.data['best_day']['calories'], 2500)
        # Exceeded 2000 goal once (Day 2)
        self.assertEqual(response.data['days_over_goal'], 1)
