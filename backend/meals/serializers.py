import re
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework import status
from meals.models import Meal

class DuplicateMealException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'A duplicate meal with the same name was logged within ±30 minutes.'
    default_code = 'duplicate_meal'

class MealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meal
        fields = ['id', 'name', 'calories', 'protein_g', 'carbs_g', 'fat_g', 'tags', 'eaten_at', 'source']
        read_only_fields = ['id', 'source']

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Name cannot be empty.")
        if len(value) > 100:
            raise serializers.ValidationError("Name must be 100 characters or fewer.")
        return value

    def validate_calories(self, value):
        if value < 1 or value > 5000:
            raise serializers.ValidationError("Calories must be between 1 and 5000.")
        return value

    def validate_protein_g(self, value):
        if value < 0 or value > 500:
            raise serializers.ValidationError("Protein must be between 0 and 500.")
        return value

    def validate_carbs_g(self, value):
        if value < 0 or value > 500:
            raise serializers.ValidationError("Carbs must be between 0 and 500.")
        return value

    def validate_fat_g(self, value):
        if value < 0 or value > 500:
            raise serializers.ValidationError("Fat must be between 0 and 500.")
        return value

    def validate_tags(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Tags must be a list of strings.")
        
        allowed_tags = getattr(settings, 'ALLOWED_TAGS', [])
        allowed_set = set(allowed_tags)
        for tag in value:
            if not isinstance(tag, str):
                raise serializers.ValidationError("Each tag must be a string.")
            if tag not in allowed_set:
                raise serializers.ValidationError(
                    f"Tag '{tag}' is not allowed. Choose from: {', '.join(allowed_tags)}"
                )
        return value

    def validate_eaten_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("eaten_at timestamp cannot be in the future.")
        return value

    def validate(self, data):
        # Duplicate guard (POST creation only)
        if not self.instance:
            name = data.get('name')
            eaten_at = data.get('eaten_at')
            if name and eaten_at:
                normalized_target = re.sub(r'\s+', ' ', name.strip().lower())
                
                # Check overlapping range +/- 30 minutes
                time_start = eaten_at - timedelta(minutes=30)
                time_end = eaten_at + timedelta(minutes=30)
                
                clashing_meals = Meal.objects.filter(eaten_at__range=(time_start, time_end))
                for meal in clashing_meals:
                    normalized_db = re.sub(r'\s+', ' ', meal.name.strip().lower())
                    if normalized_db == normalized_target:
                        raise DuplicateMealException()
                        
        return data
