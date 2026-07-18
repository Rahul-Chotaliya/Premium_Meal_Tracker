import os
import json
from django.core.management.base import BaseCommand
from django.conf import settings
from meals.models import Meal
from django.utils.dateparse import parse_datetime

class Command(BaseCommand):
    help = 'Seeds the database with meals from seed_meals.json'

    def handle(self, *args, **options):
        file_path = os.path.join(settings.BASE_DIR, 'seed_meals.json')

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                meals_data = json.load(f)
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f"Error parsing JSON: {e}"))
                return

        created_count = 0
        skipped_count = 0

        for item in meals_data:
            eaten_at_str = item.get('eaten_at')
            eaten_at = parse_datetime(eaten_at_str) if eaten_at_str else None
            if not eaten_at:
                self.stdout.write(self.style.WARNING(f"Skipping meal '{item.get('name')}' due to invalid date format: '{eaten_at_str}'"))
                continue

            # Check if this meal already exists at the same exact timestamp
            exists = Meal.objects.filter(
                name=item['name'],
                eaten_at=eaten_at
            ).exists()

            if not exists:
                Meal.objects.create(
                    name=item['name'],
                    calories=item['calories'],
                    protein_g=item['protein_g'],
                    carbs_g=item['carbs_g'],
                    fat_g=item['fat_g'],
                    tags=item.get('tags', []),
                    eaten_at=eaten_at,
                    source=item.get('source', 'manual')
                )
                created_count += 1
            else:
                skipped_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeding completed. Created: {created_count}, Skipped: {skipped_count}"
        ))
