#!/usr/bin/env bash
# ==============================================================================
# FunnelHub PostgreSQL Restore Script (SEC-005)
# Restores a backup file (.sql.gz or .sql.gz.gpg) into PostgreSQL.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    # Load environment variables safely without executing arbitrary shell syntax
    while IFS= read -r line || [[ -n "${line}" ]]; do
        line="$(echo "${line}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
        [[ -z "${line}" || "${line}" =~ ^# ]] && continue
        if [[ "${line}" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            var_key="${BASH_REMATCH[1]}"
            var_val="${BASH_REMATCH[2]}"
            if [[ "${var_val}" =~ ^\"(.*)\"$ ]]; then
                var_val="${BASH_REMATCH[1]}"
            elif [[ "${var_val}" =~ ^\'(.*)\'$ ]]; then
                var_val="${BASH_REMATCH[1]}"
            fi
            if [[ -z "${!var_key:-}" ]]; then
                export "${var_key}=${var_val}"
            fi
        fi
    done < "${ENV_FILE}"
fi

COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_ROOT}/docker-compose.prod.yml}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
    COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
fi

POSTGRES_DB="${POSTGRES_DB:-funnelhub}"
POSTGRES_USER="${POSTGRES_USER:-funnelhub}"
BACKUP_ENCRYPTION_PASSPHRASE="${BACKUP_ENCRYPTION_PASSPHRASE:-}"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <path-to-backup-file> [--force]" >&2
    echo "Example: $0 ./backups/funnelhub_backup_20261012_030000.sql.gz.gpg" >&2
    exit 1
fi

BACKUP_FILE="$1"
FORCE_FLAG="${2:-}"

if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "ERROR: Backup file '${BACKUP_FILE}' does not exist!" >&2
    exit 1
fi

echo "=== FunnelHub PostgreSQL Restore ==="
echo "Target DB:    ${POSTGRES_DB} (user: ${POSTGRES_USER})"
echo "Backup file:  ${BACKUP_FILE}"

if [[ "${FORCE_FLAG}" != "--force" && "${FORCE_FLAG}" != "-y" ]]; then
    read -r -p "WARNING: This will overwrite data in database '${POSTGRES_DB}'. Continue? [y/N] " confirmation
    if [[ "${confirmation}" != "y" && "${confirmation}" != "Y" ]]; then
        echo "Restore cancelled by user."
        exit 0
    fi
fi

# Decrypt and decompress pipeline directly into psql
if [[ "${BACKUP_FILE}" == *.gpg ]]; then
    echo "Decrypting and restoring GPG backup..."
    if [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE}" ]]; then
        gpg --batch --quiet --decrypt --passphrase "${BACKUP_ENCRYPTION_PASSPHRASE}" "${BACKUP_FILE}" \
            | gzip -d \
            | docker compose -f "${COMPOSE_FILE}" exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
    else
        gpg --quiet --decrypt "${BACKUP_FILE}" \
            | gzip -d \
            | docker compose -f "${COMPOSE_FILE}" exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
    fi
elif [[ "${BACKUP_FILE}" == *.gz ]]; then
    echo "Restoring gzip backup..."
    gzip -d -c "${BACKUP_FILE}" \
        | docker compose -f "${COMPOSE_FILE}" exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
elif [[ "${BACKUP_FILE}" == *.sql ]]; then
    echo "Restoring plain SQL backup..."
    docker compose -f "${COMPOSE_FILE}" exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < "${BACKUP_FILE}"
else
    echo "ERROR: Unrecognized backup file format. Expected .sql, .sql.gz, or .sql.gz.gpg" >&2
    exit 1
fi

echo "=== Database restore completed successfully ==="
exit 0
