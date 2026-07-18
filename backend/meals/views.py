import re
import json
import os
import requests
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.db import connection
from django.db.models import Sum, Count, Max
from django.db.models.functions import TruncDate
from django.utils.dateparse import parse_date

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from meals.models import Meal
from meals.serializers import MealSerializer
import traceback
import requests

class MealPagination(PageNumberPagination):
    page_size = 10


class MealViewSet(viewsets.ModelViewSet):
    queryset = Meal.objects.all().order_by('-eaten_at')
    serializer_class = MealSerializer
    pagination_class = MealPagination

    def get_queryset(self):
        qs = super().get_queryset()
        date_str = self.request.query_params.get('date')
        tag = self.request.query_params.get('tag')
        search = self.request.query_params.get('search')

        if date_str:
            qs = qs.filter(eaten_at__date=date_str)
        if tag:
            # Query lists inside JSONField in a database-agnostic way
            qs = qs.filter(tags__contains=[tag])
        if search:
            qs = qs.filter(name__icontains=search)
            
        return qs

    def perform_create(self, serializer):
        serializer.save(source='manual')


class MealSummaryView(APIView):
    def get(self, request):
        date_str = request.query_params.get('date')
        if not date_str:
            return Response(
                {"date": ["This query parameter is required."]}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        date_val = parse_date(date_str)
        if not date_val:
            return Response(
                {"date": ["Invalid date format. Use YYYY-MM-DD."]}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        is_postgres = 'postgresql' in connection.settings_dict['ENGINE'] or 'postgres' in connection.settings_dict['ENGINE']

        # Computed in the database with exactly one aggregation query
        if is_postgres:
            from django.contrib.postgres.aggregates import JSONBAgg
            summary = Meal.objects.filter(eaten_at__date=date_val).aggregate(
                total_calories=Sum('calories'),
                meal_count=Count('id'),
                total_protein=Sum('protein_g'),
                total_carbs=Sum('carbs_g'),
                total_fat=Sum('fat_g'),
                all_tags=JSONBAgg('tags')
            )
        else:
            # SQLite fallback: aggregate sums in one query, then fetch tags list
            summary = Meal.objects.filter(eaten_at__date=date_val).aggregate(
                total_calories=Sum('calories'),
                meal_count=Count('id'),
                total_protein=Sum('protein_g'),
                total_carbs=Sum('carbs_g'),
                total_fat=Sum('fat_g')
            )
            meals = Meal.objects.filter(eaten_at__date=date_val)
            summary['all_tags'] = [m.tags for m in meals]

        total_calories = summary['total_calories'] or 0
        goal_kcal = settings.DAILY_GOAL_KCAL
        remaining_kcal = goal_kcal - total_calories

        # Count frequencies for top_tags
        all_tags = summary.get('all_tags') or []
        flat_tags = []
        for t_list in all_tags:
            if isinstance(t_list, list):
                flat_tags.extend(t_list)

        from collections import Counter
        counter = Counter(flat_tags)
        if counter:
            max_count = max(counter.values())
            top_tags = [tag for tag, count in counter.items() if count == max_count]
        else:
            top_tags = []

        return Response({
            "date": date_str,
            "total_calories": total_calories,
            "goal_kcal": goal_kcal,
            "remaining_kcal": remaining_kcal,
            "macros": {
                "protein_g": summary['total_protein'] or 0,
                "carbs_g": summary['total_carbs'] or 0,
                "fat_g": summary['total_fat'] or 0
            },
            "meal_count": summary['meal_count'] or 0,
            "top_tags": top_tags
        })


class MealTrendsView(APIView):
    def get(self, request):
        days_str = request.query_params.get('days', '7')
        try:
            days = int(days_str)
        except ValueError:
            return Response(
                {"error": "days must be an integer between 1 and 30"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if days < 1 or days > 30:
            return Response(
                {"error": "days must be between 1 and 30"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Query 1: Find the latest meal date in the database to align trends correctly,
        # fallback to today's date if empty.
        max_date_dict = Meal.objects.aggregate(max_date=Max('eaten_at'))
        max_date_val = max_date_dict['max_date']
        
        if max_date_val:
            end_date = max_date_val.date()
        else:
            end_date = timezone.now().date()

        # Combine with today's date in case meals are logged today
        end_date = max(timezone.now().date(), end_date)
        start_date = end_date - timedelta(days=days - 1)

        # Query 2: Aggregate values grouped by date
        daily_totals = Meal.objects.filter(
            eaten_at__date__range=(start_date, end_date)
        ).annotate(
            date_only=TruncDate('eaten_at')
        ).values('date_only').annotate(
            calories=Sum('calories'),
            meal_count=Count('id')
        ).order_by('date_only')

        # Translate query results to quick-lookup dict
        db_data = {}
        for row in daily_totals:
            if row['date_only']:
                db_data[row['date_only'].strftime('%Y-%m-%d')] = {
                    'calories': row['calories'] or 0,
                    'meal_count': row['meal_count'] or 0
                }

        # Build gap-filled series
        series = []
        total_calories_sum = 0
        days_over_goal = 0
        goal_kcal = settings.DAILY_GOAL_KCAL

        for i in range(days):
            current_day = start_date + timedelta(days=i)
            date_str = current_day.strftime('%Y-%m-%d')
            
            if date_str in db_data:
                day_calories = db_data[date_str]['calories']
                day_meal_count = db_data[date_str]['meal_count']
            else:
                day_calories = 0
                day_meal_count = 0
                
            series.append({
                'date': date_str,
                'calories': day_calories,
                'meal_count': day_meal_count
            })
            
            total_calories_sum += day_calories
            if day_calories > goal_kcal:
                days_over_goal += 1

        avg_daily_kcal = round(total_calories_sum / days) if days > 0 else 0

        # Calculate best day
        best_day = {"date": "", "calories": 0}
        if series:
            max_day = max(series, key=lambda x: x['calories'])
            best_day = {
                'date': max_day['date'],
                'calories': max_day['calories']
            }

        return Response({
            "days": days,
            "series": series,
            "avg_daily_kcal": avg_daily_kcal,
            "best_day": best_day,
            "days_over_goal": days_over_goal
        })


QUICK_ADD_PROMPT = """Parse the following food text into a JSON object.
Allowed tags: vegetarian, non-vegetarian, vegan, high-protein, low-carb, snack.
JSON schema:
{{
  "name": "name of food",
  "calories": integer (1-5000),
  "protein_g": integer (0-500),
  "carbs_g": integer (0-500),
  "fat_g": integer (0-500),
  "tags": list of allowed tags
}}
Respond ONLY with raw JSON. No markdown formatting, no backticks.
Text: "{text}"
"""
class QuickAddView(APIView):

    def post(self, request):

        print("\n" + "=" * 80)
        print("QuickAddView POST called")
        print("=" * 80)

        # ---------------------------------------------------------------------
        # Step 1: Get input
        # ---------------------------------------------------------------------
        print("Request Data:", request.data)

        text = request.data.get("text")
        print("Text:", text)

        if not text:
            print("ERROR: text field missing")
            return Response(
                {"text": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------------------------------
        # Step 2: Load API Keys
        # ---------------------------------------------------------------------
        gemini_key = os.environ.get("GEMINI_API_KEY")
        groq_key = os.environ.get("GROQ_API_KEY")

        print("\nAPI Keys")
        print("Gemini Exists:", bool(gemini_key))
        print("Groq Exists:", bool(groq_key))

        if gemini_key:
            print("Gemini Key:", gemini_key[:10] + "...")
        else:
            print("Gemini Key NOT FOUND")

        if groq_key:
            print("Groq Key:", groq_key[:10] + "...")
        else:
            print("Groq Key NOT FOUND")

        parsed_data = None

        # ---------------------------------------------------------------------
        # Step 3: Gemini
        # ---------------------------------------------------------------------
        if gemini_key:

            print("\nUsing Gemini API")

            prompt = QUICK_ADD_PROMPT.format(text=text)

            print("\nPrompt:")
            print(prompt)

            url = (
                "https://generativelanguage.googleapis.com/"
                f"v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            )

            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 200,
                }
            }

            print("\nRequest URL:")
            print(url)

            print("\nPayload:")
            print(json.dumps(payload, indent=2))

            try:

                print("\nSending request to Gemini...")

                res = requests.post(
                    url,
                    json=payload,
                    timeout=30
                )

                print("\nStatus Code:", res.status_code)

                print("\nResponse Headers:")
                print(dict(res.headers))

                print("\nRaw Response:")
                print(res.text)

                # Raise error for non-200 responses
                res.raise_for_status()

                result_json = res.json()

                print("\nParsed Response JSON:")
                print(json.dumps(result_json, indent=2))

                if "candidates" not in result_json:
                    print("ERROR: No candidates found.")
                else:
                    print("Candidates found.")

                text_response = (
                    result_json["candidates"][0]
                    ["content"]["parts"][0]["text"]
                )

                print("\nLLM Returned:")
                print(text_response)

                try:
                    parsed_data = json.loads(text_response.strip())

                    print("\nSuccessfully Parsed JSON")
                    print(parsed_data)

                except json.JSONDecodeError:
                    print("\nJSON Parsing Failed")
                    traceback.print_exc()

            except Exception:
                print("\nGemini Exception:")
                traceback.print_exc()

        # ---------------------------------------------------------------------
        # Step 4: Groq
        # ---------------------------------------------------------------------
        elif groq_key:

            print("\nUsing Groq API")

            prompt = QUICK_ADD_PROMPT.format(text=text)

            url = "https://api.groq.com/openai/v1/chat/completions"

            headers = {
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "llama3-8b-8192",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.0,
                "max_tokens": 200,
                "response_format": {
                    "type": "json_object"
                }
            }

            print("\nPayload:")
            print(json.dumps(payload, indent=2))

            try:

                res = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=30
                )

                print("Status Code:", res.status_code)
                print("Response:")
                print(res.text)

                res.raise_for_status()

                result_json = res.json()

                print(json.dumps(result_json, indent=2))

                text_response = result_json["choices"][0]["message"]["content"]

                print("LLM Returned:")
                print(text_response)

                parsed_data = json.loads(text_response.strip())

                print("Parsed Data:")
                print(parsed_data)

            except Exception:
                print("\nGroq Exception:")
                traceback.print_exc()

        else:
            print("\nNo API Keys Found!")

        # ---------------------------------------------------------------------
        # Step 5: Check parsed data
        # ---------------------------------------------------------------------
        print("\nParsed Data Before Serializer:")
        print(parsed_data)

        if not parsed_data:
            print("ERROR: parsed_data is None")

            return Response(
                {
                    "error": "Failed to parse text via LLM. Make sure API keys are configured."
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

        # ---------------------------------------------------------------------
        # Step 6: Inject eaten_at
        # ---------------------------------------------------------------------
        if "eaten_at" not in parsed_data:
            parsed_data["eaten_at"] = timezone.now().isoformat()
            print("Injected current datetime")

        print("\nFinal Parsed Data:")
        print(json.dumps(parsed_data, indent=2))

        # ---------------------------------------------------------------------
        # Step 7: Serializer
        # ---------------------------------------------------------------------
        serializer = MealSerializer(data=parsed_data)

        if serializer.is_valid():

            print("\nSerializer is VALID")

            serializer.save(source="ai")

            print("Meal Saved Successfully")

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        print("\nSerializer Errors:")
        print(serializer.errors)

        return Response(
            serializer.errors,
            status=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

# class QuickAddView(APIView):
#     def post(self, request):
#         text = request.data.get('text')
#         if not text:
#             return Response(
#                 {"text": ["This field is required."]}, 
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         gemini_key = os.environ.get("GEMINI_API_KEY")
#         groq_key = os.environ.get("GROQ_API_KEY")
#         parsed_data = None
#         print("DEBUG Gemini key: ", gemini_key)
#         print("DEBUG Groq key: ", groq_key)
#         if gemini_key:
#             url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
#             payload = {
#                 "contents": [{
#                     "parts": [{"text": QUICK_ADD_PROMPT.format(text=text)}]
#                 }],
#                 "generationConfig": {
#                     "responseMimeType": "application/json",
#                     "maxOutputTokens": 200,
#                 }
#             }
#             try:
#                 res = requests.post(url, json=payload, timeout=10)
#                 if res.status_code == 200:
#                     result_json = res.json()
#                     text_response = result_json['candidates'][0]['content']['parts'][0]['text']
#                     parsed_data = json.loads(text_response.strip())
#             except Exception as e:
#                 print("DEBUG Error: ", str(e))
#                 pass
#         elif groq_key:
#             url = "https://api.groq.com/openai/v1/chat/completions"
#             headers = {
#                 "Authorization": f"Bearer {groq_key}",
#                 "Content-Type": "application/json"
#             }
#             payload = {
#                 "model": "llama3-8b-8192",
#                 "messages": [
#                     {"role": "user", "content": QUICK_ADD_PROMPT.format(text=text)}
#                 ],
#                 "temperature": 0.0,
#                 "max_tokens": 200,
#                 "response_format": {"type": "json_object"}
#             }
#             try:
#                 res = requests.post(url, json=payload, headers=headers, timeout=10)
#                 if res.status_code == 200:
#                     result_json = res.json()
#                     text_response = result_json['choices'][0]['message']['content']
#                     parsed_data = json.loads(text_response.strip())
#             except Exception:
#                 pass

#         if not parsed_data:
#             return Response(
#                 {"error": "Failed to parse text via LLM. Make sure API keys are configured."}, 
#                 status=status.HTTP_422_UNPROCESSABLE_ENTITY
#             )

#         # Inject default current time if not parsed
#         if 'eaten_at' not in parsed_data:
#             parsed_data['eaten_at'] = timezone.now().isoformat()

#         serializer = MealSerializer(data=parsed_data)
#         if serializer.is_valid():
#             serializer.save(source='ai')
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#         else:
#             return Response(serializer.errors, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
