#!/usr/bin/env bash
# Restore the latest encrypted database backup into a disposable, isolated container.
set -euo pipefail

root="${FUNNELHUB_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
backup_dir="${BACKUP_DIR:-$root/backups}"
backup="$(find "$backup_dir" -maxdepth 1 -type f -name 'funnelhub_backup_*.sql.gz.gpg' -printf '%f\n' | sort | tail -1)"
if [[ -z "$backup" ]]; then
    echo 'ERROR: no encrypted backup found' >&2
    exit 1
fi

# Read only the relevant dotenv value; never source the production environment.
passphrase="$(python3 - "$root/.env" <<'PY'
import pathlib, sys
for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    if line.startswith("BACKUP_ENCRYPTION_PASSPHRASE="):
        value = line.split("=", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        print(value)
        break
PY
)"
if [[ -z "$passphrase" ]]; then
    echo 'ERROR: backup passphrase is not configured' >&2
    exit 1
fi

name="funnelhub-restore-check-$$"
trap 'docker rm -fv "$name" >/dev/null 2>&1 || true' EXIT
image="$(docker inspect --format '{{.Config.Image}}' funnelhub-postgres-1)"
docker run -d --network none --name "$name" -e POSTGRES_HOST_AUTH_METHOD=trust "$image" >/dev/null
ready=0
for _ in {1..60}; do
    if docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
done
if [[ "$ready" != 1 ]]; then echo 'ERROR: temporary database failed to start' >&2; exit 1; fi
printf '%s' "$passphrase" | gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 0 \
    --decrypt "$backup_dir/$backup" | gzip -dc | \
    docker exec -i "$name" psql -q -v ON_ERROR_STOP=1 -U postgres -d postgres >/dev/null
docker exec "$name" psql -v ON_ERROR_STOP=1 -U postgres -d postgres -Atc \
    'SELECT count(*) FROM leads; SELECT count(*) FROM funnel_states;'
touch "$backup_dir/.last-successful-restore"
echo "OK: restored $backup in an isolated temporary database"
