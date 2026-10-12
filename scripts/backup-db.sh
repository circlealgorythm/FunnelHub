#!/usr/bin/env bash
# ==============================================================================
# FunnelHub Automated PostgreSQL Backup Script (SEC-005)
# Zero-downtime, transaction-consistent dump with compression, GPG encryption,
# and retention rotation.
# ==============================================================================
set -euo pipefail

# 1. Configuration & Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    # Load environment variables without overriding already-exported ones
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_ROOT}/docker-compose.prod.yml}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
    COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
fi

POSTGRES_DB="${POSTGRES_DB:-funnelhub}"
POSTGRES_USER="${POSTGRES_USER:-funnelhub}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
BACKUP_ENCRYPTION_PASSPHRASE="${BACKUP_ENCRYPTION_PASSPHRASE:-}"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
BASE_NAME="funnelhub_backup_${TIMESTAMP}"
TMP_DUMP="${BACKUP_DIR}/${BASE_NAME}.tmp.sql.gz"

echo "=== [${TIMESTAMP}] Starting FunnelHub PostgreSQL Backup ==="
echo "Project root: ${PROJECT_ROOT}"
echo "Database:     ${POSTGRES_DB} (user: ${POSTGRES_USER})"
echo "Backup dir:   ${BACKUP_DIR}"

# 2. Check Docker Compose & PostgreSQL Container
if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: 'docker' command not found." >&2
    exit 1
fi

# 3. Create Compressed Backup via pg_dump
echo "Dumping database '${POSTGRES_DB}'..."
if ! docker compose -f "${COMPOSE_FILE}" exec -T postgres pg_dump \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges | gzip -9 > "${TMP_DUMP}"; then
    echo "ERROR: Database dump failed!" >&2
    rm -f "${TMP_DUMP}"
    exit 2
fi

# Check file size (must be > 100 bytes)
DUMP_SIZE="$(wc -c < "${TMP_DUMP}" | tr -d ' ')"
if [[ "${DUMP_SIZE}" -le 100 ]]; then
    echo "ERROR: Dump file is empty or suspiciously small (${DUMP_SIZE} bytes)!" >&2
    rm -f "${TMP_DUMP}"
    exit 3
fi

# 4. Optional GPG Encryption
if [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE}" ]]; then
    FINAL_FILE="${BACKUP_DIR}/${BASE_NAME}.sql.gz.gpg"
    echo "Encrypting dump with GPG (AES256)..."
    gpg --batch --yes --symmetric \
        --cipher-algo AES256 \
        --passphrase "${BACKUP_ENCRYPTION_PASSPHRASE}" \
        -o "${FINAL_FILE}" "${TMP_DUMP}"
    rm -f "${TMP_DUMP}"
else
    FINAL_FILE="${BACKUP_DIR}/${BASE_NAME}.sql.gz"
    mv "${TMP_DUMP}" "${FINAL_FILE}"
    echo "NOTICE: Backup is compressed but unencrypted (set BACKUP_ENCRYPTION_PASSPHRASE for AES256 encryption)."
fi

chmod 600 "${FINAL_FILE}"
FINAL_SIZE="$(wc -c < "${FINAL_FILE}" | tr -d ' ')"
echo "Backup successfully created: ${FINAL_FILE} (${FINAL_SIZE} bytes)"

# 5. Retention Rotation (Delete backups older than RETENTION_DAYS)
echo "Rotating backups older than ${RETENTION_DAYS} days..."
DELETED_COUNT=0
while IFS= read -r old_backup; do
    if [[ -n "${old_backup}" ]]; then
        echo "Removing obsolete backup: ${old_backup}"
        rm -f "${old_backup}"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    fi
done < <(find "${BACKUP_DIR}" -type f \( -name "funnelhub_backup_*.sql.gz" -o -name "funnelhub_backup_*.sql.gz.gpg" \) -mtime +"${RETENTION_DAYS}")

echo "Rotation complete. Deleted: ${DELETED_COUNT} old backup(s)."
echo "=== Backup completed successfully ==="
exit 0
