from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.postgres.indexes import GinIndex

class Meal(models.Model):
    SOURCE_CHOICES = (
        ('manual', 'Manual Entry'),
        ('ai', 'AI Quick-Add'),
    )

    name = models.CharField(max_length=100)
    calories = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5000)]
    )
    protein_g = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(500)]
    )
    carbs_g = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(500)]
    )
    fat_g = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(500)]
    )
    tags = models.JSONField(default=list)
    eaten_at = models.DateTimeField()
    source = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        default='manual'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['eaten_at']),
            # A GIN index on tags (JSONField) is ideal for JSON containment lookups like tags__contains.
            # In PostgreSQL, this optimizes searching for specific tags.
            GinIndex(fields=['tags']),
        ]

    def __str__(self):
        return f"{self.name} ({self.calories} kcal) on {self.eaten_at}"
