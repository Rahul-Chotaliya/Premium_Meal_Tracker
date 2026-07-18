#!/bin/sh

echo "Waiting for database..."
# Simple database connection loop using standard python library socket check
until python -c "import socket, os; s = socket.socket(); s.connect((os.environ.get('DB_HOST', 'db'), int(os.environ.get('DB_PORT', 5432))))" 2>/dev/null; do
  sleep 0.5
done
echo "Database connection established!"

# Run migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Seed data
echo "Seeding default data..."
python manage.py seed_db

# Start Django development server
echo "Starting backend server..."
exec python manage.py runserver 0.0.0.0:8000
