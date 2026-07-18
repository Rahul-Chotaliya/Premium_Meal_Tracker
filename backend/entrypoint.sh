#!/bin/sh

# Only block and wait for database socket if DB_HOST is explicitly defined (e.g., local docker-compose)
if [ -n "$DB_HOST" ]; then
  echo "Waiting for database at $DB_HOST:${DB_PORT:-5432}..."
  until python -c "import socket, os; s = socket.socket(); s.connect((os.environ.get('DB_HOST'), int(os.environ.get('DB_PORT', 5432))))" 2>/dev/null; do
    sleep 0.5
  done
  echo "Database connection established!"
else
  echo "No DB_HOST specified. Skipping TCP socket wait loop (production database)."
fi

# Run migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Seed data
echo "Seeding default data..."
python manage.py seed_db

# Start server: Use Gunicorn in production if PORT is provided, fallback to runserver for local dev
if [ -n "$PORT" ]; then
  echo "Starting production server with Gunicorn on port $PORT..."
  exec gunicorn meal_tracker.wsgi:application --bind 0.0.0.0:$PORT
else
  echo "Starting development server on port 8000..."
  exec python manage.py runserver 0.0.0.0:8000
fi
