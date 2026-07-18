# Plate Meal Tracker

Plate is a premium, full-stack meal tracking dashboard. It allows users to log meals manually or via AI, tracks metrics (calories and macronutrients) against a daily goal, filters records, and visualizes a 7-day historical calorie trends chart.

---

## 🚀 Local Setup & Seeding

Running the entire application stack requires **zero extra steps** and automatically seeds the database on startup.

1. Ensure you have Docker and Docker Compose installed.
2. Clone this repository and navigate to the root directory.
3. Start the application services:
   ```bash
   docker compose up --build
   ```
4. Once built and started:
   - **Frontend Dashboard**: Access at [http://localhost:5173](http://localhost:5173)
   - **Backend API Docs**: Access at [http://localhost:8000/api/](http://localhost:8000/api/)
   - **Database Seeding**: The backend container automatically runs migrations and seeds the database with 50 unique meal logs from `seed_meals.json`.

---

## 🌐 Production Deployed URLs

* **Backend Live API**: `https://your-backend-app.render.com/api/` (Replace with your actual Render deployment URL)
* **Frontend Live UI**: `https://your-frontend-app.vercel.app` (Replace with your actual Vercel deployment URL)

---

## 📊 Data Model & Database Indexes

### Model Schema
* **Meal**: `id` (Primary Key), `name` (string), `calories` (int), `protein_g` (int), `carbs_g` (int), `fat_g` (int), `tags` (JSON list), `eaten_at` (UTC timestamp), `source` (choice: `manual` or `ai`).

### Added Indexes & Reasoning
1. **B-Tree Index on `eaten_at`**:
   - *Reasoning*: Almost every endpoint (listing list with date filter, daily summary calculation, and trends range aggregates) filters or groups records by `eaten_at`. Indexing this column changes linear scans into logarithmic lookups, maintaining performance at scale.
2. **PostgreSQL GIN Index on `tags`**:
   - *Reasoning*: The tag system allows selecting multiple tag filters (e.g. `vegetarian`, `high-protein`). In PostgreSQL, using a GIN (Generalized Inverted Index) on the `JSONField` optimizes list containment checks (e.g. `tags__contains=[tag]`), bypassing slow full-column parsing scans.

---

## 🔍 Key Technical Implementations

### 1. Daily Summary Aggregation (Single Query)
To avoid the N+1 select issue and memory-heavy Python loops, the daily summary is calculated in the database with exactly **one aggregation query**:

```python
# Postgres Query Structure
summary = Meal.objects.filter(eaten_at__date=date_val).aggregate(
    total_calories=Sum('calories'),
    meal_count=Count('id'),
    total_protein=Sum('protein_g'),
    total_carbs=Sum('carbs_g'),
    total_fat=Sum('fat_g'),
    all_tags=JSONBAgg('tags')
)
```
*Note: A connection-engine check detects if SQLite is used locally, falling back to aggregate sums + subquery tags to preserve cross-database test suitability.*

### 2. Trends Gap-Filling & 2-Query Limit
The trends endpoint returns a daily sum series for the last $N$ days ($N \le 30$). Gap-filling is computed using **exactly 2 queries** total:
1. **Query 1**: Finds the maximum date in the database:
   ```python
   max_date_dict = Meal.objects.aggregate(max_date=Max('eaten_at'))
   ```
   *This aligns the 7-day range to the seeded data window, keeping the charts immediately visual upon initial load rather than rendering blank spaces if checked months/years later.*
2. **Query 2**: Runs date grouping aggregates:
   ```python
   daily_totals = Meal.objects.filter(
       eaten_at__date__range=(start_date, end_date)
   ).annotate(
       date_only=TruncDate('eaten_at')
   ).values('date_only').annotate(
       calories=Sum('calories'),
       meal_count=Count('id')
   ).order_by('date_only')
   ```
3. **Gap-Filling (Python)**: The result is indexed into a dictionary. A calendar loop starting from `start_date` checks each day. If a date is missing from the database query result, Python appends a zeroed series item (`calories: 0, meal_count: 0`). Averages and top days are computed in Python over this final array.

---

## 🛠️ AI Tools Disclosures

This project was built in pair programming with **Antigravity (built by Google DeepMind)**. The AI was used for:
- Writing optimal Postgres indexing schemas.
- Scaffolding the Vite-React boilerplate structure and configuring the CSS layout grids.
- Implementing the Django request logger middleware and constructing the mathematical loops for hand-rolled SVG trends chart scaling.
- Crafting mock seed values in `seed_meals.json` matching target evaluation bounds.

---

## 📐 Tradeoffs & Gaps
- **SQLite vs Postgres JSON containment**: In local testing, SQLite handles list containment queries `tags__contains=[tag]` but does not support `JSONBAgg`. The custom fallback is written in `views.py` so local tests pass without needing a running Postgres daemon.
- **LLM Quick-Add connection timeout**: Direct API calls to Gemini and Groq endpoints are wrapped in a 10-second request timeout to prevent blocking thread locks if the LLM provider experiences outages.
