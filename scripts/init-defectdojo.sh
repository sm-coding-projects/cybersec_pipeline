#!/usr/bin/env bash
# init-defectdojo.sh — First-run bootstrap for DefectDojo
#
# Run once after the initial "docker compose up -d --build":
#
#   bash scripts/init-defectdojo.sh
#
# The script is idempotent — safe to re-run if interrupted.
# After it completes, copy the printed API token into your .env
# and restart the backend/worker:
#
#   docker compose up -d backend celery-worker

set -euo pipefail

CONTAINER="defectdojo-web"
ADMIN_USER="admin"
ADMIN_EMAIL="admin@localhost"
ADMIN_PASSWORD="${DD_ADMIN_PASSWORD:-admin}"
MAX_WAIT=180   # seconds to wait for DefectDojo DB to become available

# ── helpers ──────────────────────────────────────────────────────────────────

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "==> $*"; }

# ── pre-flight ────────────────────────────────────────────────────────────────

docker inspect "$CONTAINER" --format='{{.State.Running}}' 2>/dev/null \
  | grep -q true \
  || die "Container '$CONTAINER' is not running. Start the stack first: docker compose up -d"

# ── wait for database ─────────────────────────────────────────────────────────

log "Waiting for DefectDojo database (up to ${MAX_WAIT}s)..."
WAITED=0
until docker exec "$CONTAINER" python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dojo.settings.settings')
django.setup()
from django.db import connection
connection.cursor()
" 2>/dev/null; do
  if [ "$WAITED" -ge "$MAX_WAIT" ]; then
    die "DefectDojo database not ready after ${MAX_WAIT}s. Check: docker compose logs defectdojo-db defectdojo-web"
  fi
  echo "  ... waiting (${WAITED}s elapsed)"
  sleep 5
  WAITED=$((WAITED + 5))
done
log "Database is ready."

# ── migrations ────────────────────────────────────────────────────────────────

log "Running Django migrations..."
docker exec "$CONTAINER" python manage.py migrate --no-input

# ── admin user ────────────────────────────────────────────────────────────────

log "Creating admin user '$ADMIN_USER'..."
docker exec "$CONTAINER" python manage.py shell -c "
from django.contrib.auth.models import User
if User.objects.filter(username='${ADMIN_USER}').exists():
    print('  Admin user already exists — skipping creation.')
else:
    User.objects.create_superuser(
        username='${ADMIN_USER}',
        email='${ADMIN_EMAIL}',
        password='${ADMIN_PASSWORD}',
    )
    print('  Admin user created.')
"

# set/reset password in case this is a re-run with a different password
docker exec "$CONTAINER" python manage.py shell -c "
from django.contrib.auth.models import User
u = User.objects.get(username='${ADMIN_USER}')
u.set_password('${ADMIN_PASSWORD}')
u.save()
"

# ── product type ──────────────────────────────────────────────────────────────

log "Creating default product type..."
docker exec "$CONTAINER" python manage.py shell -c "
from dojo.models import Product_Type
if not Product_Type.objects.filter(name='External Assessment').exists():
    Product_Type(name='External Assessment').save()
    print('  Product type created.')
else:
    print('  Product type already exists — skipping.')
"

# ── API token ─────────────────────────────────────────────────────────────────

log "Retrieving API token..."
API_TOKEN=$(docker exec "$CONTAINER" python manage.py shell -c "
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
u = User.objects.get(username='${ADMIN_USER}')
token, _ = Token.objects.get_or_create(user=u)
print(token.key)
")

# ── done ──────────────────────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo " DefectDojo bootstrap complete!"
echo ""
echo "  Admin user : ${ADMIN_USER}"
echo "  Password   : ${ADMIN_PASSWORD}"
echo "  API Token  : ${API_TOKEN}"
echo ""
echo " Next steps:"
echo "  1. Add this line to your .env file:"
echo "       DEFECTDOJO_API_KEY=${API_TOKEN}"
echo ""
echo "  2. Restart the backend and worker:"
echo "       docker compose up -d backend celery-worker"
echo "============================================================"
