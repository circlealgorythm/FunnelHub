#!/bin/sh
# ROLLBACK: vosstanovlenie BD iz dampa do importa GetCourse (2026-11-06)
# Ispolzovanie: sh /tmp/gc_import/rollback_gc_import.sh
set -e

DUMP=/tmp/gc_import/pre_gc_import_20261106.dump
COMPOSE="docker compose -f /opt/funnelhub/docker-compose.prod.yml"

echo "=== ROLLBACK ==="
# Spisok seychas zapuschennyh servisov (bez postgres/redis)
RUNNING=$($COMPOSE ps --services --status running | grep -v -E '^(postgres|redis)$' | tr '\n' ' ')
echo "Services to stop: $RUNNING"

echo "=== Stop services ==="
cd /opt/funnelhub
$COMPOSE stop $RUNNING

echo "=== Recreate schema public ==="
docker exec funnelhub-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'

echo "=== Restore dump: $DUMP ==="
docker exec -i funnelhub-postgres-1 sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' < "$DUMP"

echo "=== Start services: $RUNNING ==="
$COMPOSE start $RUNNING

echo "=== Check: leads count (must be 499) ==="
docker exec funnelhub-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "select count(*) from leads"'
echo "=== ROLLBACK DONE ==="
